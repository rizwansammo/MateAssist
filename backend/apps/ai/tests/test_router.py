"""Key pool routing and metering (D-073, D-110)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ai import router
from apps.ai.engines import EngineResult, NoKeyAvailable, RateLimited
from apps.ai.models import Engine, ModelPrice, ProviderKey

pytestmark = pytest.mark.django_db


def make_key(label, engine=Engine.TEXT, **kwargs):
    key = ProviderKey(engine=engine, label=label, **kwargs)
    key.set_secret(f"sk-{label}-secret-value")
    key.save()
    return key


def test_acquire_prefers_the_never_used_key():
    used = make_key("used")
    used.last_used_at = timezone.now()
    used.save(update_fields=["last_used_at"])
    fresh = make_key("fresh")

    assert router.acquire(Engine.TEXT).pk == fresh.pk


def test_acquire_rotates_least_recently_used():
    """Round-robin: two consecutive calls must not return the same key, or one
    credential absorbs all the traffic and hits its quota alone."""
    make_key("one")
    make_key("two")

    first = router.acquire(Engine.TEXT)
    second = router.acquire(Engine.TEXT)

    assert first.pk != second.pk


def test_acquire_increments_usage():
    make_key("solo")
    key = router.acquire(Engine.TEXT)
    assert key.requests_today == 1
    assert key.last_used_at is not None


def test_revoked_keys_are_never_acquired():
    make_key("dead", status=ProviderKey.Status.REVOKED)
    with pytest.raises(NoKeyAvailable):
        router.acquire(Engine.TEXT)


def test_cooling_key_is_skipped_then_recovers():
    key = make_key("cooling")
    router.cool_down(key, reason="429")

    with pytest.raises(NoKeyAvailable):
        router.acquire(Engine.TEXT)

    # Cooldown elapses
    key.refresh_from_db()
    key.cooldown_until = timezone.now() - timedelta(seconds=1)
    key.save(update_fields=["cooldown_until"])

    recovered = router.acquire(Engine.TEXT)
    assert recovered.pk == key.pk
    assert recovered.status == ProviderKey.Status.ACTIVE
    assert recovered.cooldown_until is None


def test_quota_exhausted_key_is_skipped():
    make_key("capped", daily_quota=1, requests_today=1, quota_reset_on=timezone.now().date())
    with pytest.raises(NoKeyAvailable):
        router.acquire(Engine.TEXT)


def test_quota_resets_on_a_new_day():
    yesterday = timezone.now().date() - timedelta(days=1)
    make_key("rollover", daily_quota=1, requests_today=1, quota_reset_on=yesterday)

    key = router.acquire(Engine.TEXT)
    assert key.requests_today == 1  # reset to 0, then this call counted


def test_engines_have_separate_pools():
    """A Gemini key must never serve a DeepSeek call. Separate pools are how the
    engine contract survives at the credential layer too."""
    make_key("vision-only", engine=Engine.VISION)

    with pytest.raises(NoKeyAvailable):
        router.acquire(Engine.TEXT)

    assert router.acquire(Engine.VISION).label == "vision-only"


def test_rate_limit_cools_the_key_and_fails_over(tenant):
    """The behaviour the prototype's key-pool table promised: a 429 takes one
    key out of rotation and the next call goes elsewhere."""
    make_key("alpha")
    make_key("beta")
    calls = []

    class FakeClient:
        model = "deepseek-chat"

        def __init__(self, fail):
            self.fail = fail

        def complete(self, *a, **kw):
            calls.append(self.fail)
            if self.fail:
                raise RateLimited("429 rate limit exceeded")
            return EngineResult(
                text="ok", model="deepseek-chat", prompt_tokens=10, completion_tokens=5
            )

    order = iter([True, False])
    result = router._call_with_pool(
        Engine.TEXT,
        lambda _key: FakeClient(next(order)),
        lambda client: client.complete(),
        tenant=tenant,
        user=None,
        operation="chat",
    )

    assert result.text == "ok"
    assert calls == [True, False], "did not fail over to the second key"
    cooled = [k for k in ProviderKey.objects.all() if k.status == ProviderKey.Status.RATE_LIMITED]
    assert len(cooled) == 1


def test_every_successful_call_writes_a_usage_event(tenant):
    """D-110: no provider call without a meter reading."""
    from apps.metering.models import UsageEvent

    make_key("metered")
    ModelPrice.objects.create(
        engine=Engine.TEXT,
        model="deepseek-chat",
        input_per_1m=Decimal("0.27"),
        output_per_1m=Decimal("1.10"),
    )

    class FakeClient:
        model = "deepseek-chat"

        def complete(self, *a, **kw):
            return EngineResult(
                text="hi",
                model="deepseek-chat",
                prompt_tokens=1_000_000,
                completion_tokens=1_000_000,
            )

    router._call_with_pool(
        Engine.TEXT,
        lambda _k: FakeClient(),
        lambda c: c.complete(),
        tenant=tenant,
        user=None,
        operation="chat",
    )

    event = UsageEvent.all_objects.get()
    assert event.tenant_id == tenant.id
    assert event.prompt_tokens == 1_000_000
    # 0.27 + 1.10, straight from the ModelPrice row rather than a constant.
    assert event.cost_usd == Decimal("1.370000")


def test_unpriced_model_costs_zero_rather_than_failing(tenant):
    """A missing rate must not break a user's chat. The zero shows up in the
    dashboard as a missing price, which is the right place to notice it."""
    from apps.metering.models import compute_cost

    assert compute_cost(Engine.TEXT, "unpriced-model", prompt_tokens=5000) == Decimal("0")


@pytest.fixture
def tenant():
    from apps.tenancy.models import Tenant
    from apps.tenancy.tests.test_isolation import set_db_tenant

    created = Tenant.objects.create(name="Alpha", slug="alpha")
    set_db_tenant(created.id)
    return created
