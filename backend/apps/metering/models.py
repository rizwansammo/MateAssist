"""Usage metering (D-110, D-111).

Every provider call writes one row. No provider call without a meter reading -
that invariant is what makes the billing dashboard trustworthy rather than an
estimate.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

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


def price_for(engine: str, model: str) -> ModelPrice | None:
    """Most recent price point for a model, or None if unpriced."""
    return ModelPrice.objects.filter(engine=engine, model=model).order_by("-effective_from").first()


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
