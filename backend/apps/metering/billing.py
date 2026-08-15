"""Turning usage into an invoice (D-160).

Separate from `rollups` on purpose. Rollups answer "what did this cost us?" from
provider prices; this answers "what do we charge for it?" from billing rates.
The two numbers are never equal and must not share a code path, or a provider
repricing itself would silently move a customer's invoice.

Charging is pure usage with no plan fee, by decision: every token billed at the
rate in force, nothing else.
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from . import rollups
from .models import rate_for

_CENTS = Decimal("0.01")
_MILLION = Decimal("1000000")


def month_bounds(year: int, month: int) -> tuple[dt.datetime, dt.datetime]:
    """First instant of the month, and the first instant of the next one.

    Half-open on purpose. A closing bound of 23:59:59 on the last day drops
    everything in the final second, which is invisible until the one invoice
    where it is not.
    """
    last_day = calendar.monthrange(year, month)[1]
    start = timezone.make_aware(dt.datetime(year, month, 1))
    end = timezone.make_aware(dt.datetime(year, month, last_day)) + dt.timedelta(days=1)
    return start, end


def statement(tenant, *, year: int, month: int, alias: str = rollups.PLATFORM_ALIAS) -> dict:
    """What this workspace owes for one calendar month.

    The rate is resolved as at the FIRST day of the month being billed, not
    today. Re-running an old month must produce the same figure it produced when
    it was issued; resolving against today would quietly restate history every
    time somebody changed a price.
    """
    start, end = month_bounds(year, month)
    # The PLATFORM connection, not the request's. A statement is inherently a
    # cross-workspace operation, and on the tenant-scoped connection RLS returns
    # an empty result that reads as "this workspace used nothing" - a $0.00
    # invoice for a customer who owes money.
    summary = rollups.tenant_summary(tenant, since=start, until=end, alias=alias)

    rate = rate_for(tenant, on=start.date())
    if rate is None:
        # Explicitly not zero. A workspace with no rate configured has an
        # unknown bill, and reporting it as $0.00 would hide unbilled usage
        # behind a number that looks like a finished answer.
        return {
            "tenant": tenant.name,
            "period": f"{year:04d}-{month:02d}",
            "billable": False,
            "reason": "No billing rate has been configured.",
            "tokens": summary.total_tokens,
            "images": summary.images,
            "requests": summary.requests,
        }

    token_charge = (Decimal(summary.total_tokens) / _MILLION) * rate.per_1m_tokens
    image_charge = Decimal(summary.images) * rate.per_image

    # Rounded once, at the end. Rounding each line first and adding the results
    # drifts by a cent or two on a large month, and an invoice whose lines do
    # not add up to its total is the kind of thing a customer notices.
    total = (token_charge + image_charge).quantize(_CENTS, rounding=ROUND_HALF_UP)

    return {
        "tenant": tenant.name,
        "tenant_id": tenant.id,
        "period": f"{year:04d}-{month:02d}",
        "billable": True,
        "currency": rate.currency,
        "rate_per_1m_tokens": str(rate.per_1m_tokens),
        "rate_per_image": str(rate.per_image),
        "rate_effective_from": rate.effective_from.isoformat(),
        "rate_is_override": rate.tenant_id is not None,
        "requests": summary.requests,
        "tokens": summary.total_tokens,
        "prompt_tokens": summary.prompt_tokens,
        "completion_tokens": summary.completion_tokens,
        "images": summary.images,
        "token_charge": str(token_charge.quantize(_CENTS, rounding=ROUND_HALF_UP)),
        "image_charge": str(image_charge.quantize(_CENTS, rounding=ROUND_HALF_UP)),
        "total": str(total),
        # What the platform paid providers for the same window. Shown to the
        # platform owner only, and never to the tenant: it is the margin.
        "provider_cost": str(summary.cost_usd.quantize(_CENTS, rounding=ROUND_HALF_UP)),
        "margin": str((total - summary.cost_usd).quantize(_CENTS, rounding=ROUND_HALF_UP)),
    }


def statements(
    tenants, *, year: int, month: int, alias: str = rollups.PLATFORM_ALIAS
) -> list[dict]:
    """Every workspace for one month, heaviest bill first."""
    rows = [statement(tenant, year=year, month=month, alias=alias) for tenant in tenants]
    return sorted(rows, key=lambda row: Decimal(row.get("total", "0")), reverse=True)
