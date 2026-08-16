"""The Phase 7A gate.

    python manage.py usage_demo

Runs the reporting layer against the real database, with the real two roles, on
committed data - which is the only environment where it can be proven at all.

**Why this command exists alongside the tests.** `test_platform_rollups.py`
covers cross-tenant aggregation with committed data and both real roles, so the
claim is no longer test-less. What this command adds is the thing a test suite
cannot give: the same code exercised against the *development* database, with
whatever real traffic and prices happen to be in it, before anyone trusts a
dashboard rendered from it. Phases 4-6 each shipped a bug that a green suite did
not see (A-006), and every one surfaced the moment something was actually run.

The assertions are the point. A demo that prints numbers proves nothing - a
wrong number on a billing screen is worse than an exception, because nobody
investigates a page that renders. Every claim below fails the command loudly.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.ai.models import Engine
from apps.core.demo_guard import refuse_in_production
from apps.metering import budgets, rollups
from apps.metering.models import Operation, TenantBudget, UsageEvent
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

DEMO_MODEL = "usage-demo-model"


def _arm(tenant_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            ["" if tenant_id is None else str(tenant_id)],
        )


class Command(BaseCommand):
    help = "Phase 7A gate: prove usage rollups, tenant scoping and budget enforcement."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Leave the demo usage rows behind instead of cleaning them up.",
        )

    # -- helpers ---------------------------------------------------------

    def ok(self, message):
        self.stdout.write(self.style.SUCCESS(f"  PASS  {message}"))

    def fail(self, message):
        self.stdout.write(self.style.ERROR(f"  FAIL  {message}"))
        self.failures.append(message)

    def expect(self, condition, message):
        self.ok(message) if condition else self.fail(message)

    def head(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))

    # -- the gate --------------------------------------------------------

    def handle(self, *args, **options):
        refuse_in_production(self, what="synthetic usage events and a temporary budget")
        self.failures: list[str] = []

        tenants = list(Tenant.objects.order_by("id")[:2])
        if len(tenants) < 2:
            self.stderr.write(
                "Two tenants are required to prove cross-tenant scoping. Run seed_dev first."
            )
            sys.exit(1)
        alpha, beta = tenants

        self.head(f"Seeding demo usage  ({alpha.slug} $3.00, {beta.slug} $7.00)")
        self._seed(alpha, "1.00")
        self._seed(alpha, "2.00")
        self._seed(beta, "7.00")
        self.stdout.write("  3 usage events written")

        try:
            self._prove_tenant_scoping(alpha, beta)
            self._prove_platform_scope(alpha, beta)
            self._prove_alias_trap(alpha)
            self._prove_budgets(alpha)
            self._report(alpha)
        finally:
            if not options["keep"]:
                self._cleanup()

        self.head("Result")
        if self.failures:
            for failure in self.failures:
                self.stdout.write(self.style.ERROR(f"  - {failure}"))
            self.stderr.write(f"\n{len(self.failures)} assertion(s) failed.")
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("  Phase 7A gate passed.\n"))

    # -- steps -----------------------------------------------------------

    def _seed(self, tenant, cost):
        # set_config is transaction-scoped and management commands run in
        # autocommit, so the write needs an explicit transaction or RLS refuses
        # it. This exact omission broke ingest_demo in Phase 5.
        with tenant_context(tenant.id), transaction.atomic():
            _arm(tenant.id)
            UsageEvent.all_objects.create(
                tenant=tenant,
                engine=Engine.TEXT,
                model=DEMO_MODEL,
                operation=Operation.CHAT,
                prompt_tokens=1000,
                completion_tokens=500,
                cost_usd=Decimal(cost),
                latency_ms=1200,
            )

    def _prove_tenant_scoping(self, alpha, beta):
        self.head("1. A workspace rollup cannot cross tenants (RLS, app role)")

        with tenant_context(alpha.id), transaction.atomic():
            _arm(alpha.id)
            own = rollups.tenant_summary(alpha, since=None)
            # Adversarial: ask for Beta's figures while armed as Alpha. The
            # Python filter says Beta; the database says Alpha; the database wins.
            leaked = rollups.tenant_summary(beta, since=None)

        self.stdout.write(
            f"  armed as {alpha.slug}: own=${own.cost_usd}  leaked=${leaked.cost_usd}"
        )
        self.expect(own.cost_usd == Decimal("3.000000"), f"{alpha.slug} sees its own $3.00")
        self.expect(
            leaked.requests == 0 and leaked.cost_usd == Decimal("0"),
            f"{alpha.slug} cannot reach {beta.slug}'s rows even when asked to",
        )

    def _prove_platform_scope(self, alpha, beta):
        self.head("2. The platform rollup sees every workspace (admin role, RLS bypassed)")

        summary = rollups.platform_summary(since=None)
        rows = {row["tenant_slug"]: row for row in rollups.platform_by_tenant(since=None)}

        self.stdout.write(f"  platform total: {summary.requests} requests  ${summary.cost_usd}")
        for slug, row in sorted(rows.items()):
            self.stdout.write(f"    {slug:<16} {row['requests']:>3} req  ${row['cost_usd']}")

        self.expect(
            summary.cost_usd >= Decimal("10.000000"), "platform total includes both tenants"
        )
        self.expect(
            alpha.slug in rows and beta.slug in rows,
            "per-tenant breakdown lists both workspaces",
        )
        self.expect(
            rows.get(alpha.slug, {}).get("cost_usd") == "3.000000"
            and rows.get(beta.slug, {}).get("cost_usd") == "7.000000",
            "spend is attributed to the right workspace",
        )
        self.expect(
            DEMO_MODEL in summary.unpriced_models,
            "an unpriced model is named rather than silently costing zero",
        )

    def _prove_alias_trap(self, alpha):
        self.head("3. The alias trap that would silently zero the billing screen")

        # No tenant armed: the RLS predicate collapses to `tenant_id IS NULL`.
        _arm(None)
        blind = rollups.month_to_date_cost(alpha)
        seeing = rollups.month_to_date_cost(alpha, alias=rollups.PLATFORM_ALIAS)

        self.stdout.write(f"  default alias, no context: ${blind}   platform alias: ${seeing}")
        self.expect(
            blind == Decimal("0"),
            "default connection returns zero with no tenant armed (the trap)",
        )
        self.expect(
            seeing == Decimal("3.000000"),
            "platform alias returns the real figure - so status_for must pass it",
        )

    def _prove_budgets(self, alpha):
        self.head("4. Budget enforcement blocks on the path that spends money")

        budget, _ = TenantBudget.objects.using(rollups.PLATFORM_ALIAS).update_or_create(
            tenant=alpha,
            defaults={"monthly_tokens": 50_000, "enforce": False},
        )

        with tenant_context(alpha.id), transaction.atomic():
            _arm(alpha.id)

            # Advisory: over the cap, but must not block.
            try:
                budgets.assert_within_budget(alpha)
                self.ok("an advisory budget over its cap blocks nothing")
            except budgets.BudgetExceeded:
                self.fail("an advisory budget must not block calls")

            budget.enforce = True
            budget.save(update_fields=["enforce"])

            try:
                budgets.assert_within_budget(alpha)
                self.fail("an enforced budget over its cap must refuse the call")
            except budgets.BudgetExceeded as exc:
                self.ok(f"enforced budget refuses: spent ${exc.spent} of ${exc.cap}")

            # A zero cap means "no limit", not "spend nothing" - otherwise
            # creating a budget row would cut a workspace off instantly.
            budget.monthly_tokens = 0
            budget.save(update_fields=["monthly_tokens"])
            try:
                budgets.assert_within_budget(alpha)
                self.ok("a zero cap means no limit rather than a total outage")
            except budgets.BudgetExceeded:
                self.fail("a zero cap must not block")

            status = budgets.status_for(alpha)
            self.expect(status is not None, "budget status is reported for the dashboard")

        TenantBudget.objects.using(rollups.PLATFORM_ALIAS).filter(tenant=alpha).delete()

    def _report(self, alpha):
        self.head("5. What the dashboards will render")

        totals = rollups.platform_summary(since=None)
        self.stdout.write("  Platform, current billing month:")
        self.stdout.write(f"    requests        {totals.requests}")
        self.stdout.write(f"    tokens          {totals.total_tokens:,}")
        self.stdout.write(f"    cost            ${totals.cost_usd}")
        self.stdout.write(f"    success rate    {totals.success_rate:.1%}")
        self.stdout.write(f"    avg latency     {totals.avg_latency_ms} ms")
        if totals.unpriced_models:
            self.stdout.write(
                self.style.WARNING(f"    unpriced        {', '.join(totals.unpriced_models)}")
            )

        for row in rollups.platform_by_engine(since=None):
            self.stdout.write(
                f"    {row['engine']:<8} {row['requests']:>4} req  "
                f"{row['total_tokens']:>8,} tok  ${row['cost_usd']}"
            )

        series = rollups.platform_series(since=None)
        self.stdout.write(f"  Daily buckets: {len(series)} day(s) with usage")

    def _cleanup(self):
        deleted, _ = (
            UsageEvent.all_objects.using(rollups.PLATFORM_ALIAS).filter(model=DEMO_MODEL).delete()
        )
        self.stdout.write(f"\n  cleaned up {deleted} demo usage row(s)")
