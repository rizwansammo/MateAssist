"""Usage metering (D-110, D-111).

Every provider call writes one row. No provider call without a meter reading -
that invariant is what makes the billing dashboard trustworthy rather than an
estimate.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.ai.models import Engine, ModelPrice
from apps.tenancy.managers import TenantScopedModel


class Operation(models.TextChoices):
    CHAT = "chat", "Chat completion"
    CLASSIFY = "classify", "Intent classification"
    DESCRIBE_IMAGE = "describe_image", "Image description"
    EMBED = "embed", "Embedding"


class UsageEvent(TenantScopedModel):
    """Tenant-scoped, and therefore RLS-protected like every other tenant table.

    One workspace must not be able to infer another's volume or spend.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    engine = models.CharField(max_length=10, choices=Engine.choices)
    model = models.CharField(max_length=64)
    operation = models.CharField(max_length=20, choices=Operation.choices)

    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    image_count = models.PositiveSmallIntegerField(default=0)

    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    succeeded = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["tenant", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.engine}/{self.model} {self.operation} ${self.cost_usd}"


class TenantBudget(models.Model):
    """A monthly spend cap for one workspace (D-113).

    Deliberately NOT a TenantScopedModel. This is platform commercial
    configuration *about* a workspace, in the same category as `Tenant` itself -
    a workspace must not be able to raise or disable its own cap by writing to
    its own row. It is created and edited only through the platform-owner API.

    `enforce` defaults to False so that adding a budget is first an observation,
    not an outage. An admin sets a figure, watches the dashboard for a cycle, and
    turns enforcement on once the number looks right.
    """

    tenant = models.OneToOneField("tenancy.Tenant", on_delete=models.CASCADE, related_name="budget")
    monthly_usd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    enforce = models.BooleanField(
        default=False, help_text="Refuse provider calls once the cap is reached."
    )
    alert_at_percent = models.PositiveSmallIntegerField(
        default=80, help_text="Warn on the dashboard at this percentage of the cap."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("tenant__name",)

    def __str__(self) -> str:
        state = "enforced" if self.enforce else "advisory"
        return f"{self.tenant_id}: ${self.monthly_usd}/mo ({state})"

    @property
    def is_capped(self) -> bool:
        """A zero or negative cap means "no limit", not "spend nothing".

        The alternative reading would turn the moment an admin creates a budget
        row into a total outage for that workspace before they have typed a
        figure - a footgun disguised as strictness.
        """
        return self.monthly_usd > 0


def price_for(engine: str, model: str) -> ModelPrice | None:
    """Most recent price point for a model, or None if unpriced."""
    return ModelPrice.objects.filter(engine=engine, model=model).order_by("-effective_from").first()


class BillingRate(models.Model):
    """What a workspace is CHARGED per unit (D-160).

    Not to be confused with `ModelPrice`, which is what the platform PAYS its
    providers. Both are money per token and they are never the same number: the
    gap between them is the margin. Keeping them in one table would make it
    impossible to change a sell price without appearing to restate historical
    provider cost, or to absorb a provider increase without repricing customers.

    A null tenant is the default that applies to every workspace. A row with a
    tenant overrides it for that workspace alone, which is how a negotiated
    price is expressed without a second mechanism.

    `effective_from` makes this a history rather than a setting. Editing a rate
    in place would silently restate every invoice ever produced - a customer who
    queries last month's bill must be able to be shown the rate that was in
    force when the tokens were spent, not the one in force today.
    """

    tenant = models.ForeignKey(
        "tenancy.Tenant",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="billing_rates",
        help_text="Blank applies to every workspace. Set it to override one.",
    )

    per_1m_tokens = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0"),
        help_text="Charged per 1,000,000 tokens, prompt and completion together.",
    )
    per_image = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0"),
        help_text="Charged per screenshot read by the vision engine.",
    )

    # Unit prices, not a pricing MODE (D-169).
    #
    # A per-token/per-request toggle would force a choice and block a contract
    # that mixes them. Leaving a price at zero simply does not charge for that
    # unit, so "per request only" is a rate with tokens at zero - same table, no
    # enum, and a negotiated hybrid is expressible without new machinery.
    per_request = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0"),
        help_text="Charged per question asked, whatever its length.",
    )

    # Charged when MateAssist emails an escalation to the workspace's helpdesk.
    #
    # Counted from `escalation_sent_at` on the message, which is written once by
    # an atomic claim (D-163) - so a user clicking twice cannot be billed twice.
    # This is escalations RAISED, not tickets resolved: the helpdesk knows the
    # outcome and MateAssist has no link back to it.
    per_escalation = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0"),
        help_text="Charged per escalation emailed to the helpdesk.",
    )
    currency = models.CharField(max_length=3, default="USD")
    effective_from = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("tenant__name", "-effective_from")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "effective_from"], name="uniq_billing_rate_point"
            )
        ]

    def __str__(self) -> str:
        who = self.tenant.name if self.tenant_id else "platform default"
        return f"{who} from {self.effective_from}: {self.per_1m_tokens}/1M"


def rate_for(tenant, *, on=None) -> BillingRate | None:
    """The rate in force for a workspace on a given day.

    Tenant-specific first, then the platform default; within each, the latest
    row that had already taken effect. Returns None when nothing has been
    configured at all, which the caller must treat as "cannot bill yet" rather
    than as zero - a bill of $0.00 and a bill that could not be calculated look
    identical on a dashboard and mean opposite things.
    """
    on = on or timezone.localdate()

    for scope in ({"tenant": tenant}, {"tenant__isnull": True}):
        rate = (
            BillingRate.objects.filter(effective_from__lte=on, **scope)
            .order_by("-effective_from")
            .first()
        )
        if rate is not None:
            return rate
    return None


def compute_cost(engine: str, model: str, *, prompt_tokens=0, completion_tokens=0, images=0):
    """Cost from the database, never a hardcoded rate.

    An unpriced model yields zero rather than an exception: failing a user's
    chat request because an admin has not entered a rate would be the wrong
    trade. The zero is visible in the dashboard as a missing price.
    """
    price = price_for(engine, model)
    if price is None:
        return Decimal("0")

    million = Decimal(1_000_000)
    return (
        (Decimal(prompt_tokens) / million) * price.input_per_1m
        + (Decimal(completion_tokens) / million) * price.output_per_1m
        + Decimal(images) * price.per_image
    ).quantize(Decimal("0.000001"))
