"""Credential vault and provider pricing (D-070, D-111).

ProviderKey is platform-level, not tenant-scoped: the platform owner supplies the
credentials and every workspace's traffic flows through the same pool. Access is
restricted to PLATFORM_OWNER at the API layer.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from . import vault


class Engine(models.TextChoices):
    """The two engines, and only two (D-040/D-041/D-044)."""

    TEXT = "TEXT", "Text & Reasoning (DeepSeek)"
    VISION = "VISION", "Vision & OCR (Gemini)"


class ProviderKey(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RATE_LIMITED = "RATE_LIMITED", "Rate-limited"
        REVOKED = "REVOKED", "Revoked"

    engine = models.CharField(max_length=10, choices=Engine.choices, db_index=True)
    label = models.CharField(max_length=64)

    # The sealed credential. There is no serializer field that reads this and no
    # endpoint that returns it (D-072) - write-only is the absence of a code
    # path, not a flag that could be misconfigured.
    ciphertext = models.TextField(editable=False)
    last4 = models.CharField(max_length=8, editable=False)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    weight = models.PositiveSmallIntegerField(default=1)
    daily_quota = models.PositiveIntegerField(
        null=True, blank=True, help_text="Requests per day. Null means unmetered."
    )
    requests_today = models.PositiveIntegerField(default=0)
    quota_reset_on = models.DateField(null=True, blank=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("engine", "label")
        constraints = [
            models.UniqueConstraint(fields=["engine", "label"], name="uniq_key_engine_label")
        ]
        indexes = [models.Index(fields=["engine", "status"])]

    def __str__(self) -> str:
        return f"{self.engine}:{self.label}"

    # -- sealing ---------------------------------------------------------

    @property
    def vault_context(self) -> str:
        """Binds the ciphertext to this row, so a blob cannot be moved between
        keys and silently decrypt as another engine's credential."""
        return f"providerkey:{self.engine}:{self.label}"

    def set_secret(self, secret: str) -> None:
        secret = secret.strip()
        if not secret:
            raise ValueError("Refusing to store an empty credential.")
        self.ciphertext = vault.seal(secret, context=self.vault_context)
        self.last4 = vault.last4(secret)

    def reveal(self) -> str:
        """Decrypt for an outbound provider call. Never for display."""
        return vault.open_sealed(self.ciphertext, context=self.vault_context)

    # -- pool state ------------------------------------------------------

    @property
    def masked(self) -> str:
        return f"{'•' * 11}{self.last4}"

    def is_available(self, now=None) -> bool:
        now = now or timezone.now()
        if self.status == self.Status.REVOKED:
            return False
        if self.cooldown_until and self.cooldown_until > now:
            return False
        return not (self.daily_quota is not None and self.requests_today >= self.daily_quota)


class ModelPrice(models.Model):
    """Per-model rates.

    In the database and editable in admin (D-111). Hardcoding provider prices
    guarantees the cost dashboard silently lies the first time a rate changes.
    """

    engine = models.CharField(max_length=10, choices=Engine.choices)
    model = models.CharField(max_length=64)
    input_per_1m = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    output_per_1m = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    per_image = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    currency = models.CharField(max_length=3, default="USD")
    effective_from = models.DateField(default=timezone.now)

    class Meta:
        ordering = ("engine", "model", "-effective_from")
        constraints = [
            models.UniqueConstraint(
                fields=["engine", "model", "effective_from"], name="uniq_price_point"
            )
        ]

    def __str__(self) -> str:
        return f"{self.model} @ {self.effective_from}"
