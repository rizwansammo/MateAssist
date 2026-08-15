"""Charging a workspace for what it used (D-160).

Billing is the one place where a quiet arithmetic mistake becomes a customer
dispute rather than a bug report, so these tests are about the money: which rate
applied, when it applied from, and what happens when there is no rate at all.

The distinction being defended throughout: `ModelPrice` is what the platform
PAYS providers, `BillingRate` is what a workspace is CHARGED. They are different
numbers and must never be confused.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from apps.ai.models import Engine, ModelPrice
from apps.metering import billing
from apps.metering.models import BillingRate, Operation, UsageEvent, rate_for
from apps.tenancy.models import Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

# transaction=True and both aliases: a statement reads on the `admin`
# connection, which is a separate session and cannot see anything this test's
# transaction has not committed. Phase 7A hit the same wall - the alias is real,
# so the test has to be too.
pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "admin"])

YEAR, MONTH = 2026, 7


@pytest.fixture
def tenants():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")
    return alpha, beta


def log_usage(tenant, *, prompt=0, completion=0, images=0, when=None, cost="0"):
    """A usage event inside the billed month unless told otherwise."""
    when = when or timezone.make_aware(dt.datetime(YEAR, MONTH, 15, 12, 0))

    # The arming and the insert must share a transaction. `set_config(..., true)`
    # is transaction-scoped, and under transaction=True every statement commits
    # on its own - so without this the setting is gone by the time the INSERT
    # runs and the RLS WITH CHECK clause rejects the row.
    with transaction.atomic():
        set_db_tenant(tenant.id)
        event = UsageEvent.all_objects.create(
            tenant=tenant,
            engine=Engine.TEXT,
            model="llama-3.3-70b-versatile",
            operation=Operation.CHAT,
            prompt_tokens=prompt,
            completion_tokens=completion,
            image_count=images,
            cost_usd=Decimal(cost),
        )
        # auto_now_add ignores an explicit value, so the timestamp is corrected
        # afterwards - otherwise every event lands today and the month filter
        # under test never actually excludes anything.
        UsageEvent.all_objects.filter(pk=event.pk).update(created_at=when)
    return event


# --------------------------------------------------------- rate resolution --


def test_the_platform_default_applies_when_there_is_no_override(tenants):
    alpha, _ = tenants
    BillingRate.objects.create(tenant=None, per_1m_tokens=Decimal("15"))

    rate = rate_for(alpha)
    assert rate.per_1m_tokens == Decimal("15")
    assert rate.tenant_id is None


def test_a_tenant_override_beats_the_default(tenants):
    """How a negotiated price is expressed, without a second mechanism."""
    alpha, beta = tenants
    BillingRate.objects.create(tenant=None, per_1m_tokens=Decimal("15"))
    BillingRate.objects.create(tenant=alpha, per_1m_tokens=Decimal("9"))

    assert rate_for(alpha).per_1m_tokens == Decimal("9")
    assert rate_for(beta).per_1m_tokens == Decimal("15")


def test_the_latest_rate_that_has_taken_effect_wins(tenants):
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("15"), effective_from=dt.date(2026, 1, 1)
    )
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("12"), effective_from=dt.date(2026, 6, 1)
    )

    assert rate_for(alpha, on=dt.date(2026, 7, 1)).per_1m_tokens == Decimal("12")


def test_a_future_rate_is_not_applied_early(tenants):
    """A price announced for next quarter must not bill this one."""
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("15"), effective_from=dt.date(2026, 1, 1)
    )
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("20"), effective_from=dt.date(2026, 10, 1)
    )

    assert rate_for(alpha, on=dt.date(2026, 7, 1)).per_1m_tokens == Decimal("15")


def test_no_rate_at_all_resolves_to_none(tenants):
    alpha, _ = tenants
    assert rate_for(alpha) is None


# ----------------------------------------------------------------- amounts --


def test_a_month_is_charged_at_the_configured_rate(tenants):
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None,
        per_1m_tokens=Decimal("15"),
        per_image=Decimal("0.02"),
        effective_from=dt.date(2026, 1, 1),
    )
    log_usage(alpha, prompt=400_000, completion=600_000, images=10)

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    assert result["billable"] is True
    assert result["tokens"] == 1_000_000
    # 1M tokens at $15, plus 10 images at $0.02.
    assert result["token_charge"] == "15.00"
    assert result["image_charge"] == "0.20"
    assert result["total"] == "15.20"


def test_usage_outside_the_month_is_not_billed(tenants):
    """The bound is half-open. A closing bound of 23:59:59 drops the last
    second of the month, which nobody notices until the invoice it lands in."""
    alpha, _ = tenants
    BillingRate.objects.create(tenant=None, per_1m_tokens=Decimal("15"))

    log_usage(alpha, prompt=1_000_000)
    log_usage(alpha, prompt=5_000_000, when=timezone.make_aware(dt.datetime(YEAR, MONTH + 1, 1)))
    log_usage(
        alpha,
        prompt=7_000_000,
        when=timezone.make_aware(dt.datetime(YEAR, MONTH, 1)) - dt.timedelta(seconds=1),
    )

    assert billing.statement(alpha, year=YEAR, month=MONTH)["tokens"] == 1_000_000


def test_one_workspace_is_never_billed_for_another(tenants):
    alpha, beta = tenants
    BillingRate.objects.create(tenant=None, per_1m_tokens=Decimal("15"))
    log_usage(alpha, prompt=1_000_000)
    log_usage(beta, prompt=9_000_000)

    assert billing.statement(alpha, year=YEAR, month=MONTH)["tokens"] == 1_000_000
    assert billing.statement(beta, year=YEAR, month=MONTH)["tokens"] == 9_000_000


def test_the_rate_is_resolved_as_at_the_billed_month_not_today(tenants):
    """Re-running July must produce July's figure. Resolving against today
    would silently restate every historical invoice on the next price change."""
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("10"), effective_from=dt.date(2026, 1, 1)
    )
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("30"), effective_from=dt.date(2026, 12, 1)
    )
    log_usage(alpha, prompt=1_000_000)

    assert billing.statement(alpha, year=YEAR, month=MONTH)["total"] == "10.00"


def test_an_unconfigured_workspace_is_not_billed_as_zero(tenants):
    """A bill of $0.00 and a bill that could not be calculated look identical on
    a dashboard and mean opposite things. Usage is still reported, so unbilled
    consumption is visible rather than hidden behind a confident number."""
    alpha, _ = tenants
    log_usage(alpha, prompt=5_000_000)

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    assert result["billable"] is False
    assert "total" not in result
    assert result["tokens"] == 5_000_000


def test_margin_is_the_gap_between_charge_and_provider_cost(tenants):
    """The reason BillingRate and ModelPrice are separate tables."""
    alpha, _ = tenants
    ModelPrice.objects.create(
        engine=Engine.TEXT,
        model="llama-3.3-70b-versatile",
        input_per_1m=Decimal("0"),
        output_per_1m=Decimal("0"),
    )
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("15"), effective_from=dt.date(2026, 1, 1)
    )
    log_usage(alpha, prompt=1_000_000, cost="4.00")

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    assert result["total"] == "15.00"
    assert result["provider_cost"] == "4.00"
    assert result["margin"] == "11.00"


def test_rounding_happens_once_at_the_end(tenants):
    """Rounding each line before adding drifts by a cent on a large month, and
    an invoice whose lines do not add up to its total gets queried."""
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None,
        per_1m_tokens=Decimal("15"),
        per_image=Decimal("0.005"),
        effective_from=dt.date(2026, 1, 1),
    )
    log_usage(alpha, prompt=333_333, images=3)

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    # 333,333 tokens at $15/1M = 4.999995, plus 3 images at $0.005 = 0.015.
    # Rounded once: 5.014995 -> 5.01.
    assert result["total"] == "5.01"


def test_statements_are_ordered_by_size(tenants):
    alpha, beta = tenants
    BillingRate.objects.create(
        tenant=None, per_1m_tokens=Decimal("15"), effective_from=dt.date(2026, 1, 1)
    )
    log_usage(alpha, prompt=1_000_000)
    log_usage(beta, prompt=4_000_000)

    rows = billing.statements([alpha, beta], year=YEAR, month=MONTH)
    assert [row["tenant"] for row in rows] == ["Beta", "Alpha"]


# ------------------------------------------------------ unit prices (D-169) --


def escalate_in_month(tenant, *, count=1, when=None):
    """Messages stamped as escalated inside the billed window."""
    from apps.chat.models import Conversation, Message
    from apps.chat.models import Role as MessageRole

    when = when or timezone.make_aware(dt.datetime(YEAR, MONTH, 10, 9, 0))
    with transaction.atomic():
        set_db_tenant(tenant.id)
        conversation = Conversation.all_objects.create(tenant=tenant, title="Locked out")
        for index in range(count):
            message = Message.all_objects.create(
                tenant=tenant,
                conversation=conversation,
                role=MessageRole.ASSISTANT,
                text=f"escalation {index}",
                proposed_escalation={"subject": "Help"},
            )
            Message.all_objects.filter(pk=message.pk).update(escalation_sent_at=when)


def test_a_per_request_contract_needs_no_token_price(tenants):
    """The reason unit prices beat a mode toggle: "per request only" is just a
    rate with tokens at zero, using the same table and no new machinery."""
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None,
        per_1m_tokens=Decimal("0"),
        per_request=Decimal("0.25"),
        effective_from=dt.date(2026, 1, 1),
    )
    log_usage(alpha, prompt=800_000)
    log_usage(alpha, prompt=900_000)

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    assert result["token_charge"] == "0.00"
    assert result["request_charge"] == "0.50"
    assert result["total"] == "0.50"


def test_escalations_are_charged_when_a_price_is_set(tenants):
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None,
        per_1m_tokens=Decimal("0"),
        per_escalation=Decimal("2"),
        effective_from=dt.date(2026, 1, 1),
    )
    escalate_in_month(alpha, count=3)

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    assert result["escalations"] == 3
    assert result["escalation_charge"] == "6.00"
    assert result["total"] == "6.00"


def test_an_unsent_proposal_is_not_charged(tenants):
    """A drafted escalation the user never sent has cost the helpdesk nothing
    and must not appear on an invoice."""
    from apps.chat.models import Conversation, Message
    from apps.chat.models import Role as MessageRole

    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None, per_escalation=Decimal("2"), effective_from=dt.date(2026, 1, 1)
    )
    with transaction.atomic():
        set_db_tenant(alpha.id)
        conversation = Conversation.all_objects.create(tenant=alpha, title="Draft only")
        Message.all_objects.create(
            tenant=alpha,
            conversation=conversation,
            role=MessageRole.ASSISTANT,
            text="drafted, never sent",
            proposed_escalation={"subject": "Help"},
        )

    result = billing.statement(alpha, year=YEAR, month=MONTH)
    assert result["escalations"] == 0
    assert result["total"] == "0.00"


def test_escalations_outside_the_month_are_not_charged(tenants):
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None, per_escalation=Decimal("2"), effective_from=dt.date(2026, 1, 1)
    )
    escalate_in_month(alpha, count=1)
    escalate_in_month(
        alpha, count=4, when=timezone.make_aware(dt.datetime(YEAR, MONTH + 1, 2, 9, 0))
    )

    assert billing.statement(alpha, year=YEAR, month=MONTH)["escalations"] == 1


def test_one_workspaces_escalations_are_never_billed_to_another(tenants):
    alpha, beta = tenants
    BillingRate.objects.create(
        tenant=None, per_escalation=Decimal("2"), effective_from=dt.date(2026, 1, 1)
    )
    escalate_in_month(alpha, count=1)
    escalate_in_month(beta, count=5)

    assert billing.statement(alpha, year=YEAR, month=MONTH)["escalations"] == 1
    assert billing.statement(beta, year=YEAR, month=MONTH)["escalations"] == 5


def test_every_unit_price_adds_up(tenants):
    """A contract can mix them, which is the whole point of not having a mode."""
    alpha, _ = tenants
    BillingRate.objects.create(
        tenant=None,
        per_1m_tokens=Decimal("15"),
        per_request=Decimal("0.10"),
        per_image=Decimal("0.02"),
        per_escalation=Decimal("2"),
        effective_from=dt.date(2026, 1, 1),
    )
    log_usage(alpha, prompt=500_000, completion=500_000, images=5)
    escalate_in_month(alpha, count=2)

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    # 1M tokens @15 = 15.00, 1 request @0.10, 5 images @0.02 = 0.10, 2 @2 = 4.00
    assert result["token_charge"] == "15.00"
    assert result["request_charge"] == "0.10"
    assert result["image_charge"] == "0.10"
    assert result["escalation_charge"] == "4.00"
    assert result["total"] == "19.20"


def test_a_workspace_with_no_rate_still_reports_its_escalations(tenants):
    """Unbilled usage has to stay visible, or it hides behind a number that
    looks like a finished answer."""
    alpha, _ = tenants
    escalate_in_month(alpha, count=2)

    result = billing.statement(alpha, year=YEAR, month=MONTH)

    assert result["billable"] is False
    assert result["escalations"] == 2
