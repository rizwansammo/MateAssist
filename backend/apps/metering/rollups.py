"""Usage aggregation (D-112).

Two scopes, and the difference between them is a security boundary rather than
a query parameter:

* **Tenant scope** runs on the `default` connection as the NOSUPERUSER app role.
  RLS is active, so a rollup physically cannot sum another workspace's rows even
  if the Python filter were wrong.
* **Platform scope** runs on the `admin` connection, which is a superuser and
  therefore *bypasses RLS entirely*. That is the only way to answer "spend across
  all tenants", and it is also the one place in this codebase where cross-tenant
  reads are possible at all. Every function that uses it is named `platform_*`
  and every route that reaches one is gated by `IsPlatformOwner`.

The naming is deliberate: a reviewer should never have to check which connection
a rollup used. `platform_` in the name means "this crosses tenants".
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.ai.models import ModelPrice

from .models import TenantBudget, UsageEvent

# The RLS-bypassing connection. Referenced by name in one place so it is
# greppable: `git grep PLATFORM_ALIAS` finds every cross-tenant read.
PLATFORM_ALIAS = "admin"

_ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=6))


# ------------------------------------------------------------- windows -------


def month_start(when: dt.datetime | None = None) -> dt.datetime:
    """First instant of the current UTC month - the billing period boundary."""
    now = when or timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def window(days: int | None = None, *, since=None, until=None):
    """Resolve a reporting window. Defaults to the current billing month.

    Returns (since, until) with until exclusive.
    """
    now = timezone.now()
    if since is None:
        since = now - dt.timedelta(days=days) if days else month_start(now)
    return since, until or now


# ------------------------------------------------------------- shapes -------


@dataclass
class Summary:
    """Totals for one window. `unpriced_models` is not decoration.

    `compute_cost` returns zero for a model with no `ModelPrice` row, because
    failing a user's chat because an admin has not entered a rate would be the
    wrong trade (see metering.models). The consequence is that a dashboard can
    show a confidently small number that is simply incomplete. Carrying the
    unpriced model names alongside the total lets the UI say "$4.10 across 3
    models, 1 unpriced" instead of quietly understating spend.
    """

    requests: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    images: int = 0
    cost_usd: Decimal = Decimal("0")
    avg_latency_ms: int = 0
    unpriced_models: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def success_rate(self) -> float:
        return round((self.requests - self.failed) / self.requests, 4) if self.requests else 0.0

    def as_dict(self, *, include_model_names: bool = False) -> dict:
        """Serialise for the API.

        `include_model_names` defaults to **False**, and the default is the
        point (D-136). Model identifiers name the vendor - `gemini-flash-latest`
        says Google as plainly as a logo would - and a workspace is not told
        which provider serves its engines. Only the platform surface passes True.

        Tenants still learn that something is unpriced, via a count, because
        that affects whether they can trust their own cost figure. They just do
        not learn what it is called.
        """
        payload: dict = {
            "requests": self.requests,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "images": self.images,
            "cost_usd": str(self.cost_usd),
            "avg_latency_ms": self.avg_latency_ms,
            "unpriced_model_count": len(self.unpriced_models),
        }
        if include_model_names:
            payload["unpriced_models"] = self.unpriced_models
        return payload


_AGGREGATES = {
    "requests": Count("id"),
    "failed": Count("id", filter=Q(succeeded=False)),
    "prompt_tokens": Coalesce(Sum("prompt_tokens"), 0),
    "completion_tokens": Coalesce(Sum("completion_tokens"), 0),
    "images": Coalesce(Sum("image_count"), 0),
    "cost_usd": Coalesce(Sum("cost_usd"), _ZERO),
    "avg_latency_ms": Coalesce(Avg("latency_ms"), 0.0),
}


def _base(*, tenant=None, since=None, until=None, alias="default"):
    """The queryset every rollup starts from.

    `all_objects` with an explicit tenant filter, never the tenant-scoped
    manager: that manager reads a ContextVar, and a caller that armed the
    database session without the Python context - a management command, a Celery
    task - would silently get an empty queryset. Phase 6 shipped exactly that bug
    in the escalation transcript. RLS remains the guarantee; this filter is
    defence in depth.
    """
    queryset = UsageEvent.all_objects.using(alias)
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    if since is not None:
        queryset = queryset.filter(created_at__gte=since)
    if until is not None:
        queryset = queryset.filter(created_at__lt=until)
    return queryset


def _unpriced(queryset) -> list[str]:
    """Models that produced usage but have no price row, so contribute zero."""
    seen = set(queryset.values_list("engine", "model").distinct())
    if not seen:
        return []
    priced = set(
        ModelPrice.objects.using(queryset.db)
        .filter(model__in={model for _engine, model in seen})
        .values_list("engine", "model")
    )
    return sorted({model for pair in seen - priced for model in [pair[1]]})


def _summarise(queryset) -> Summary:
    row = queryset.aggregate(**_AGGREGATES)
    return Summary(
        requests=row["requests"],
        failed=row["failed"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        images=row["images"],
        cost_usd=row["cost_usd"],
        avg_latency_ms=int(row["avg_latency_ms"] or 0),
        unpriced_models=_unpriced(queryset),
    )


def _grouped(queryset, *fields_) -> list[dict]:
    rows = queryset.values(*fields_).annotate(**_AGGREGATES).order_by("-cost_usd", "-requests")
    return [
        {
            **{f: row[f] for f in fields_},
            "requests": row["requests"],
            "failed": row["failed"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "total_tokens": row["prompt_tokens"] + row["completion_tokens"],
            "images": row["images"],
            "cost_usd": str(row["cost_usd"]),
            "avg_latency_ms": int(row["avg_latency_ms"] or 0),
        }
        for row in rows
    ]


def _series(queryset) -> list[dict]:
    """Daily buckets. Sparse - days with no usage are simply absent, and the UI
    fills the gaps. Emitting zero rows server-side would mean generating a date
    range in SQL for no benefit."""
    rows = (
        queryset.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(**_AGGREGATES)
        .order_by("day")
    )
    return [
        {
            "day": row["day"].isoformat(),
            "requests": row["requests"],
            "failed": row["failed"],
            "total_tokens": row["prompt_tokens"] + row["completion_tokens"],
            "cost_usd": str(row["cost_usd"]),
        }
        for row in rows
    ]


# ------------------------------------------------------- tenant scope --------


def tenant_summary(tenant, *, since=None, until=None, alias="default") -> Summary:
    return _summarise(_base(tenant=tenant, since=since, until=until, alias=alias))


def tenant_by_engine(tenant, *, since=None, until=None) -> list[dict]:
    return _grouped(_base(tenant=tenant, since=since, until=until), "engine")


def tenant_by_model(tenant, *, since=None, until=None) -> list[dict]:
    return _grouped(_base(tenant=tenant, since=since, until=until), "engine", "model")


def tenant_by_operation(tenant, *, since=None, until=None) -> list[dict]:
    return _grouped(_base(tenant=tenant, since=since, until=until), "operation")


def tenant_series(tenant, *, since=None, until=None) -> list[dict]:
    return _series(_base(tenant=tenant, since=since, until=until))


def month_to_date_cost(tenant, *, alias="default") -> Decimal:
    """Spend since the start of the billing month.

    Not cached: a stale figure is unbounded overspend, which is the thing the cap
    exists to prevent.

    **`alias` is load-bearing.** On `default`, RLS resolves rows against the
    armed `app.tenant_id`; during a tenant request that is correct and is the
    strongest possible check. But a *platform owner* asking "how much has Acme
    spent?" has no tenant context armed, so the predicate collapses to
    `tenant_id IS NULL` and the sum comes back as zero - a budget dashboard
    quietly reporting that every workspace has spent nothing. Platform callers
    must pass PLATFORM_ALIAS. The explicit `filter(tenant=...)` in `_base` is
    what keeps that safe.
    """
    row = _base(tenant=tenant, since=month_start(), alias=alias).aggregate(
        total=Coalesce(Sum("cost_usd"), _ZERO)
    )
    return row["total"]


def month_to_date_tokens(tenant, *, alias="default") -> int:
    """Tokens used since the start of the billing month.

    `alias` is load-bearing for the same reason as the cost version above: a
    platform owner has no tenant armed, so on the default connection RLS would
    report zero for every workspace.
    """
    row = _base(tenant=tenant, since=month_start(), alias=alias).aggregate(
        prompt=Coalesce(Sum("prompt_tokens"), 0),
        completion=Coalesce(Sum("completion_tokens"), 0),
    )
    return int(row["prompt"]) + int(row["completion"])


# ----------------------------------------------------- platform scope --------
# Everything below reads across tenants on the RLS-bypassing connection.


def platform_summary(*, since=None, until=None) -> Summary:
    return _summarise(_base(since=since, until=until, alias=PLATFORM_ALIAS))


def platform_by_engine(*, since=None, until=None) -> list[dict]:
    return _grouped(_base(since=since, until=until, alias=PLATFORM_ALIAS), "engine")


def platform_by_model(*, since=None, until=None) -> list[dict]:
    return _grouped(_base(since=since, until=until, alias=PLATFORM_ALIAS), "engine", "model")


def platform_series(*, since=None, until=None) -> list[dict]:
    return _series(_base(since=since, until=until, alias=PLATFORM_ALIAS))


def platform_by_tenant(*, since=None, until=None) -> list[dict]:
    """Per-workspace spend - the Billing screen's main table."""
    rows = _grouped(
        _base(since=since, until=until, alias=PLATFORM_ALIAS).annotate(
            tenant_name=F("tenant__name"),
            tenant_slug=F("tenant__slug"),
            tenant_plan=F("tenant__plan"),
        ),
        "tenant_id",
        "tenant_name",
        "tenant_slug",
        "tenant_plan",
    )
    budgets = {
        budget.tenant_id: budget for budget in TenantBudget.objects.using(PLATFORM_ALIAS).all()
    }
    for row in rows:
        budget = budgets.get(row["tenant_id"])
        row["monthly_budget_tokens"] = budget.monthly_tokens if budget else None
        row["budget_enforced"] = bool(budget and budget.enforce)
    return rows
