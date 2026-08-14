"""Cross-tenant aggregation, exercised for real (D-112).

Separate module because these tests are **transactional**, and that is the whole
point of them.

The `admin` alias is a genuinely separate connection authenticated as the
database superuser - measured, not assumed: `current_user=mateassist`,
`is_superuser=on`, and `connections['default'].connection is not
connections['admin'].connection`. That superuser status is what lets the
platform surface read across tenants at all, since RLS does not apply to it.

Being a separate connection also means it cannot see the default alias's
*uncommitted* writes. Under an ordinary transactional test every `platform_*`
rollup therefore returns zero, and the reporting layer looks broken when it is
working perfectly. `transaction=True` commits the fixture data so the second
connection can see it, at the cost of a slower truncate-based teardown.

The tenant-scoped half lives in test_rollups.py and stays non-transactional,
because it needs the opposite thing: RLS refusing to cross a boundary.
"""

from decimal import Decimal

import pytest
from django.db import transaction

from apps.ai.models import Engine
from apps.metering import rollups
from apps.metering.models import Operation, UsageEvent
from apps.tenancy.models import Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "admin"])


def usage(tenant, cost, *, model="platform-test-model"):
    """Write one event with RLS armed for the row.

    The explicit transaction is required: `set_config(..., true)` is
    transaction-scoped, and these tests run in autocommit, so without it the
    arming is gone before the INSERT and the policy refuses the row.
    """
    with transaction.atomic():
        set_db_tenant(tenant.id)
        UsageEvent.all_objects.create(
            tenant=tenant,
            engine=Engine.TEXT,
            model=model,
            operation=Operation.CHAT,
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=Decimal(cost),
            latency_ms=1200,
        )


@pytest.fixture
def two_workspaces():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    usage(alpha, "1.00")
    usage(alpha, "2.00")
    usage(beta, "7.00")

    set_db_tenant(None)
    return alpha, beta


def test_the_admin_alias_really_is_a_superuser_connection():
    """Guards the premise of every other test in this module.

    If the platform alias ever stops being a superuser - or starts sharing the
    app role's connection - the rollups below would return zero and the tests
    would fail for a reason that has nothing to do with the aggregation code.
    Asserting the premise makes that failure legible.
    """
    from django.db import connections

    with connections[rollups.PLATFORM_ALIAS].cursor() as cursor:
        cursor.execute("SELECT current_setting('is_superuser')")
        assert (
            cursor.fetchone()[0] == "on"
        ), "the platform alias must bypass RLS, or cross-tenant reporting cannot work"

    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT current_setting('is_superuser')")
        assert (
            cursor.fetchone()[0] == "off"
        ), "the app role must NOT bypass RLS, or tenant isolation is decorative"


def test_platform_rollup_sees_every_workspace(two_workspaces):
    """Alpha spent $3, Beta spent $7. The platform total is $10."""
    summary = rollups.platform_summary()

    assert summary.requests == 3
    assert summary.cost_usd == Decimal("10.000000")


def test_platform_by_tenant_attributes_spend_correctly(two_workspaces):
    rows = {row["tenant_slug"]: row for row in rollups.platform_by_tenant()}

    assert rows["alpha"]["cost_usd"] == "3.000000"
    assert rows["beta"]["cost_usd"] == "7.000000"
    assert rows["alpha"]["requests"] == 2


def test_the_alias_argument_is_what_makes_platform_spend_visible(two_workspaces):
    """The bug this argument exists to prevent.

    A platform owner has no tenant context armed. On the default connection the
    RLS predicate collapses to `tenant_id IS NULL`, so month-to-date spend comes
    back as zero for every workspace - silently, with no error, on a billing
    screen. Passing PLATFORM_ALIAS is the difference between a real figure and a
    confident lie.
    """
    alpha, _ = two_workspaces
    set_db_tenant(None)

    assert rollups.month_to_date_cost(alpha) == Decimal("0")
    assert rollups.month_to_date_cost(alpha, alias=rollups.PLATFORM_ALIAS) == Decimal("3.000000")


def test_budget_status_reports_real_spend_from_the_platform_surface(two_workspaces):
    """`status_for` shipped with this bug and the gate caught it."""
    from apps.metering import budgets
    from apps.metering.models import TenantBudget

    alpha, _ = two_workspaces
    TenantBudget.objects.using(rollups.PLATFORM_ALIAS).create(
        tenant=alpha, monthly_usd=Decimal("10.00"), enforce=False
    )
    set_db_tenant(None)

    blind = budgets.status_for(alpha)
    seeing = budgets.status_for(alpha, alias=rollups.PLATFORM_ALIAS)

    assert blind["spent_usd"] == "0"
    assert seeing["spent_usd"] == "3.000000"
    assert seeing["percent_used"] == 30.0


def test_platform_series_buckets_across_tenants(two_workspaces):
    series = rollups.platform_series()

    assert len(series) == 1, "all three events are today"
    assert series[0]["cost_usd"] == "10.000000"
    assert series[0]["requests"] == 3
