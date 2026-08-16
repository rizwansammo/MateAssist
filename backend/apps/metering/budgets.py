"""Budget enforcement (D-113, revised D-172).

Caps are counted in TOKENS. They were counted in provider dollars, which is a
figure that stays at zero unless someone has entered every provider's price
list - so the cap never fired and the feature looked configured while doing
nothing. Tokens are measured directly on every call and are the unit the
product is sold in.

A cap is only meaningful if it is checked on the path that spends the budget.
That path is `router._call_with_pool`, so the check lives here and is called from
there - not in a view, where a background task or a management command would
walk straight past it.

**Why this is not cached.** Month-to-date usage is one indexed aggregate over
`(tenant, -created_at)` and it runs only when an enforcing budget exists. A cache
would make the check cheaper and also make it wrong: a 60-second stale figure is
60 seconds of unbounded overspend, which is precisely the thing the cap exists to
prevent. Correctness wins over a query that the index already answers quickly.
"""

from __future__ import annotations


class BudgetExceeded(Exception):
    """Raised before a provider call when a workspace is over its monthly cap.

    Carries the figures so the API can render a useful message rather than a
    bare 402 - an end user seeing "the assistant is unavailable" with no reason
    files a support ticket that costs more than the overage did.
    """

    def __init__(self, *, tenant, spent: int, cap: int):
        self.tenant = tenant
        self.spent = spent
        self.cap = cap
        super().__init__(
            f"{tenant} has used {spent:,} of its {cap:,} monthly tokens. "
            f"Raise the cap or disable enforcement to continue."
        )


def budget_for(tenant, *, alias="default"):
    """The workspace's budget row, or None. Never raises on a missing row -
    most tenants will not have one."""
    from .models import TenantBudget

    if tenant is None:
        return None
    return TenantBudget.objects.using(alias).filter(tenant=tenant).first()


def status_for(tenant, *, alias="default") -> dict | None:
    """Budget state for a dashboard: cap, spend, percentage, and whether the cap
    is actually enforced. None when no budget is configured.

    Pass `alias=rollups.PLATFORM_ALIAS` from the platform surface. A platform
    owner has no tenant context armed, so on the default connection RLS would
    return zero spend for every workspace - a dashboard that is confidently
    wrong rather than visibly broken.
    """
    from .rollups import month_to_date_tokens

    budget = budget_for(tenant, alias=alias)
    if budget is None:
        return None

    spent = month_to_date_tokens(tenant, alias=alias)
    percent = (spent / budget.monthly_tokens * 100) if budget.is_capped else 0.0
    return {
        "monthly_tokens": budget.monthly_tokens,
        "spent_tokens": spent,
        "percent_used": round(percent, 2),
        "enforce": budget.enforce,
        "alert_at_percent": budget.alert_at_percent,
        "alerting": budget.is_capped and percent >= budget.alert_at_percent,
        "exceeded": budget.is_capped and spent >= budget.monthly_tokens,
    }


def assert_within_budget(tenant) -> None:
    """Gate a provider call. Raises BudgetExceeded, or returns quietly.

    Three separate conditions must hold before this blocks anything: a budget
    row exists, `enforce` is on, and the cap is a positive figure. An advisory
    budget - the default - shows on the dashboard and stops nothing.
    """
    from apps.audit.models import Level, record

    from .rollups import month_to_date_tokens

    budget = budget_for(tenant)
    if budget is None or not budget.enforce or not budget.is_capped:
        return

    spent = month_to_date_tokens(tenant)
    if spent < budget.monthly_tokens:
        return

    # Audited, because a workspace being cut off is an operational event someone
    # will have to explain later.
    record(
        "budget.blocked",
        tenant=tenant,
        level=Level.WARN,
        target=str(tenant),
        spent_tokens=spent,
        cap_tokens=budget.monthly_tokens,
    )
    raise BudgetExceeded(tenant=tenant, spent=spent, cap=budget.monthly_tokens)
