"""Key pool and the metered call path (D-073, D-110).

Every provider call in the system goes through call_text/call_vision. That is
what makes "no provider call without a meter reading" an invariant rather than a
convention - there is no second way to reach an engine.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.models import Level, record

from .engines import EngineError, NoKeyAvailable, RateLimited
from .engines.factory import build_text_engine, build_vision_engine
from .models import Engine, ProviderKey

logger = logging.getLogger(__name__)

COOLDOWN = timedelta(minutes=15)


def _reset_quota_if_new_day(key: ProviderKey, today) -> bool:
    if key.quota_reset_on != today:
        key.quota_reset_on = today
        key.requests_today = 0
        return True
    return False


@transaction.atomic
def acquire(engine: str) -> ProviderKey:
    """Claim the least-recently-used available key for an engine.

    FOR UPDATE SKIP LOCKED so concurrent workers take different keys instead of
    serialising on the same row - the difference between a pool and a queue.
    """
    now = timezone.now()
    today = now.date()

    candidates = (
        ProviderKey.objects.select_for_update(skip_locked=True)
        .filter(engine=engine)
        .exclude(status=ProviderKey.Status.REVOKED)
        .order_by(models_nulls_first(), "-weight")
    )

    for key in candidates:
        changed = _reset_quota_if_new_day(key, today)

        if key.cooldown_until and key.cooldown_until <= now:
            key.cooldown_until = None
            key.status = ProviderKey.Status.ACTIVE
            changed = True

        if not key.is_available(now):
            if changed:
                key.save(
                    update_fields=["quota_reset_on", "requests_today", "cooldown_until", "status"]
                )
            continue

        key.last_used_at = now
        key.requests_today += 1
        key.status = ProviderKey.Status.ACTIVE
        key.cooldown_until = None
        key.save(
            update_fields=[
                "last_used_at",
                "requests_today",
                "status",
                "cooldown_until",
                "quota_reset_on",
            ]
        )
        return key

    raise NoKeyAvailable(f"No usable {engine} key: all are revoked, cooling down or over quota.")


def models_nulls_first():
    """Least-recently-used first; a never-used key sorts ahead of all others."""
    from django.db.models import F

    return F("last_used_at").asc(nulls_first=True)


def cool_down(key: ProviderKey, *, reason: str = "rate_limited") -> None:
    key.status = ProviderKey.Status.RATE_LIMITED
    key.cooldown_until = timezone.now() + COOLDOWN
    key.save(update_fields=["status", "cooldown_until"])
    record(
        "vault.cooldown",
        level=Level.WARN,
        target=str(key),
        engine=key.engine,
        label=key.label,
        reason=reason,
        until=key.cooldown_until.isoformat(),
    )


def _meter(*, tenant, user, engine, model, operation, result, succeeded=True):
    """Write the UsageEvent. Never raises - see the note in audit.record."""
    if tenant is None:
        return None  # platform-level calls have no workspace to bill
    try:
        from apps.metering.models import UsageEvent, compute_cost

        return UsageEvent.all_objects.create(
            tenant=tenant,
            user=user,
            engine=engine,
            model=model,
            operation=operation,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            image_count=result.image_count,
            cost_usd=compute_cost(
                engine,
                model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                images=result.image_count,
            ),
            latency_ms=result.latency_ms,
            request_id=result.raw_id,
            succeeded=succeeded,
        )
    except Exception:  # noqa: BLE001
        logger.exception("metering write failed for %s/%s", engine, model)
        return None


def _call_with_pool(engine_name, build_client, invoke, *, tenant, user, operation, max_attempts=3):
    """Acquire, call, and on a 429 cool the key down and try the next one.

    build_client receives the ProviderKey and its plaintext, so the client is
    chosen from the key's own provider/base_url/model (A-010) rather than being
    fixed per engine. Failing over between keys can therefore also fail over
    between vendors.
    """
    # D-113: checked here rather than in a view, because a view is not the only
    # thing that spends money. A Celery task or a management command that called
    # a view-level check would walk straight past it; nothing reaches an engine
    # without passing through this function.
    from apps.metering.budgets import assert_within_budget

    assert_within_budget(tenant)

    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            key = acquire(engine_name)
        except NoKeyAvailable:
            if last_error:
                # Preserve the TYPE, not just the text. Every key being
                # rate-limited is still a rate-limit problem, and the user-facing
                # message is chosen by exception type - flattening this into a
                # generic EngineError would tell the user "something went wrong"
                # when the honest answer is "we are busy, try again shortly".
                raise RateLimited(
                    f"{engine_name} pool exhausted after {attempt} attempt(s): {last_error}"
                ) from last_error
            raise

        client = build_client(key, key.reveal())
        try:
            result = invoke(client)
        except RateLimited as exc:
            cool_down(key, reason=str(exc)[:120])
            last_error = exc
            continue
        except EngineError:
            # Meter the failure too: a provider outage that costs latency and
            # shows up as zero usage looks like nobody used the product.
            _meter(
                tenant=tenant,
                user=user,
                engine=engine_name,
                model=client.model,
                operation=operation,
                result=_empty_result(),
                succeeded=False,
            )
            raise

        _meter(
            tenant=tenant,
            user=user,
            engine=engine_name,
            model=result.model,
            operation=operation,
            result=result,
        )
        return result

    if isinstance(last_error, RateLimited):
        raise RateLimited(
            f"{engine_name}: every key was rate-limited across {max_attempts} attempts"
        ) from last_error
    raise EngineError(f"{engine_name} call failed after {max_attempts} attempts: {last_error}")


def _empty_result():
    from .engines import EngineResult

    return EngineResult()


def call_text(messages, *, tenant=None, user=None, tools=None, operation="chat", **kwargs):
    """The only way to reach a text engine, whichever vendor serves the role."""
    return _call_with_pool(
        Engine.TEXT,
        build_text_engine,
        lambda client: client.complete(messages, tools=tools, **kwargs),
        tenant=tenant,
        user=user,
        operation=operation,
    )


def call_vision(image_bytes, *, mime_type, purpose="runbook", tenant=None, user=None):
    """The only way to reach a vision engine - and the only place image bytes exist."""
    return _call_with_pool(
        Engine.VISION,
        build_vision_engine,
        lambda client: client.describe(image_bytes, mime_type=mime_type, purpose=purpose),
        tenant=tenant,
        user=user,
        operation="describe_image",
    )
