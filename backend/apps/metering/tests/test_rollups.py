"""Usage aggregation and budgets (D-112, D-113).

The tests that matter here are the scoping ones. An aggregation bug does not
crash - it returns a number. A wrong number on a billing dashboard is worse than
an exception, because nobody investigates a page that renders.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.ai.models import Engine, ModelPrice
from apps.metering import budgets, rollups
from apps.metering.models import Operation, TenantBudget, UsageEvent, compute_cost
from apps.tenancy.models import Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

# Declared so that touching the `admin` alias does not raise
# DatabaseOperationForbidden. It does NOT give these tests the owner's
# credentials: `admin` is a MIRROR of `default` in test settings, which makes
# Django hand both aliases the same app-role connection. See
# test_platform_reads_cannot_be_proven_in_process for what that costs.
pytestmark = pytest.mark.django_db(databases=["default", "admin"])

User = get_user_model()


def usage(
    tenant, *, model="gemini-flash-latest", prompt=1000, completion=500, cost="0.10", ok=True
):
    """Write one event under its own tenant context - the policy's WITH CHECK
    clause refuses a row belonging to a tenant you cannot read."""
    set_db_tenant(tenant.id)
    event = UsageEvent.all_objects.create(
        tenant=tenant,
        engine=Engine.TEXT,
        model=model,
        operation=Operation.CHAT,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_usd=Decimal(cost),
        latency_ms=1200,
        succeeded=ok,
    )
    return event


@pytest.fixture
def two_workspaces():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    usage(alpha, cost="1.00")
    usage(alpha, cost="2.00")
    usage(beta, cost="7.00")

    set_db_tenant(None)
    return alpha, beta


# ------------------------------------------------------------- scoping ------


def test_tenant_rollup_cannot_see_another_workspace(two_workspaces):
    """The whole reason the tenant rollups run on the RLS-enforced connection.

    Alpha spent $3 and Beta spent $7. Armed as Alpha, the database must refuse
    to let any aggregate reach Beta's rows.
    """
    alpha, _beta = two_workspaces
    set_db_tenant(alpha.id)

    summary = rollups.tenant_summary(alpha)

    assert summary.requests == 2
    assert summary.cost_usd == Decimal("3.000000")


def test_a_deliberately_wrong_filter_still_cannot_cross_tenants(two_workspaces):
    """Adversarial: ask for Beta's figures while armed as Alpha.

    The Python filter says Beta. RLS says Alpha. The database wins and the
    answer is empty - which is what makes this isolation rather than a
    convention.
    """
    alpha, beta = two_workspaces
    set_db_tenant(alpha.id)

    leaked = rollups.tenant_summary(beta)

    assert leaked.requests == 0
    assert leaked.cost_usd == Decimal("0")


def test_platform_reads_cannot_be_proven_in_process(two_workspaces):
    """**Read this before "fixing" a platform rollup that returns zero here.**

    In test settings `admin` is declared as `TEST: {"MIRROR": "default"}`, which
    makes Django hand both aliases the *same connection object* - the one
    authenticated as the NOSUPERUSER app role. The superuser connection that
    makes `platform_*` work in production therefore does not exist inside the
    test suite, and every cross-tenant rollup comes back empty.

    MIRROR is not a mistake to be removed. Without it the two aliases get
    separate connections, and a non-transactional test's uncommitted writes on
    `default` are invisible to `admin` - so the rollups would read zero for a
    different reason, and every test that triggers a platform-scope audit write
    would have to declare a second database.

    The consequence is stated plainly: **this suite cannot verify cross-tenant
    aggregation.** That is done against the real database, with both real roles
    and committed data, by `manage.py usage_demo` - the Phase 7A gate. This is
    the same principle as A-006: a green suite is not evidence that something
    works, and four separate bugs in this project were invisible until something
    was actually run.
    """
    set_db_tenant(None)

    assert rollups.platform_summary().requests == 0, (
        "If this ever returns rows, the admin alias has stopped mirroring and "
        "the platform tests above can - and should - be made real."
    )


def test_month_to_date_on_the_default_alias_is_blind_without_a_context(two_workspaces):
    """Documents the trap that the platform surface has to work around.

    With no tenant armed, the RLS predicate collapses to `tenant_id IS NULL`, so
    a spend query on the default connection returns zero for every workspace -
    silently, with no error. This is not a bug being asserted as correct; it is
    the reason `status_for` and `month_to_date_cost` take an `alias`, and why the
    platform surface passes PLATFORM_ALIAS. A regression would mean the billing
    screen confidently reporting that nobody has spent anything.
    """
    alpha, _ = two_workspaces
    set_db_tenant(None)

    assert rollups.month_to_date_cost(alpha) == Decimal("0")

    # Armed as Alpha, the same call on the same alias finds the money.
    set_db_tenant(alpha.id)
    assert rollups.month_to_date_cost(alpha) == Decimal("3.000000")


# ------------------------------------------------------------ reporting -----


def test_unpriced_models_are_named_rather_than_silently_zero(two_workspaces):
    """compute_cost returns 0 for an unpriced model on purpose. A dashboard that
    shows that 0 without saying why is understating spend."""
    alpha, _ = two_workspaces
    set_db_tenant(alpha.id)

    summary = rollups.tenant_summary(alpha)

    assert "gemini-flash-latest" in summary.unpriced_models


def test_a_priced_model_disappears_from_the_unpriced_list(two_workspaces):
    alpha, _ = two_workspaces
    ModelPrice.objects.create(
        engine=Engine.TEXT,
        model="gemini-flash-latest",
        input_per_1m=Decimal("0.10"),
        output_per_1m=Decimal("0.40"),
    )
    set_db_tenant(alpha.id)

    assert rollups.tenant_summary(alpha).unpriced_models == []


def test_failed_calls_are_counted_but_do_not_vanish_from_totals():
    """A provider outage that shows as zero usage looks like nobody used the
    product. Failures are metered, and the success rate exposes them."""
    tenant = Tenant.objects.create(name="Gamma", slug="gamma")
    usage(tenant, cost="1.00", ok=True)
    usage(tenant, cost="0.00", ok=False)

    summary = rollups.tenant_summary(tenant)

    assert summary.requests == 2
    assert summary.failed == 1
    assert summary.success_rate == 0.5


def test_series_buckets_by_day():
    tenant = Tenant.objects.create(name="Delta", slug="delta")
    usage(tenant, cost="1.00")
    usage(tenant, cost="2.00")

    series = rollups.tenant_series(tenant)

    assert len(series) == 1, "both events are today, so they share a bucket"
    assert series[0]["cost_usd"] == "3.000000"
    assert series[0]["requests"] == 2


def test_cost_comes_from_the_database_not_a_constant():
    ModelPrice.objects.create(
        engine=Engine.TEXT,
        model="priced-model",
        input_per_1m=Decimal("1.00"),
        output_per_1m=Decimal("2.00"),
    )
    cost = compute_cost(
        Engine.TEXT, "priced-model", prompt_tokens=1_000_000, completion_tokens=500_000
    )
    assert cost == Decimal("2.000000")  # 1.00 + (0.5 * 2.00)


# -------------------------------------------------------------- budgets -----


@pytest.fixture
def spent_workspace():
    tenant = Tenant.objects.create(name="Epsilon", slug="epsilon")
    usage(tenant, cost="10.00")
    set_db_tenant(tenant.id)
    return tenant


def test_an_advisory_budget_blocks_nothing(spent_workspace):
    """`enforce` defaults to False so that adding a budget is an observation,
    not an outage."""
    TenantBudget.objects.create(tenant=spent_workspace, monthly_usd=Decimal("5.00"), enforce=False)

    budgets.assert_within_budget(spent_workspace)  # must not raise


def test_an_enforced_budget_refuses_the_call_once_it_is_reached(spent_workspace):
    TenantBudget.objects.create(tenant=spent_workspace, monthly_usd=Decimal("5.00"), enforce=True)

    with pytest.raises(budgets.BudgetExceeded) as excinfo:
        budgets.assert_within_budget(spent_workspace)

    # The figures travel with the exception so the API can say why, rather than
    # leaving a user with an unexplained dead assistant.
    assert excinfo.value.spent == Decimal("10.000000")
    assert excinfo.value.cap == Decimal("5.00")


def test_an_enforced_budget_allows_calls_below_the_cap(spent_workspace):
    TenantBudget.objects.create(tenant=spent_workspace, monthly_usd=Decimal("50.00"), enforce=True)
    budgets.assert_within_budget(spent_workspace)  # must not raise


def test_a_zero_cap_means_no_limit_rather_than_spend_nothing(spent_workspace):
    """Otherwise creating a budget row would cut a workspace off before the
    admin had typed a figure."""
    TenantBudget.objects.create(tenant=spent_workspace, monthly_usd=Decimal("0"), enforce=True)
    budgets.assert_within_budget(spent_workspace)  # must not raise


def test_a_workspace_with_no_budget_is_never_blocked(spent_workspace):
    budgets.assert_within_budget(spent_workspace)


def test_budget_status_reports_percentage_and_alert_state(spent_workspace):
    TenantBudget.objects.create(
        tenant=spent_workspace,
        monthly_usd=Decimal("20.00"),
        enforce=True,
        alert_at_percent=40,
    )

    status = budgets.status_for(spent_workspace)

    assert status["spent_usd"] == "10.000000"
    assert status["percent_used"] == 50.0
    assert status["alerting"] is True
    assert status["exceeded"] is False


def test_budget_status_is_none_when_unconfigured(spent_workspace):
    assert budgets.status_for(spent_workspace) is None
