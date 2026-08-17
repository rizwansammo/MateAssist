"""Platform-level configuration.

Nothing here is tenant-owned, so nothing here carries a tenant_id or an RLS
policy. These are settings *about* the platform, edited only through the
platform-owner API - the same category as `Tenant` itself.
"""

from django.db import models


class PlatformSettings(models.Model):
    """How MateAssist itself sends email (D-175).

    Distinct from the per-workspace SMTP on `Tenant`. That sends a customer's
    escalations, from their domain. This sends OUR mail: password reset codes,
    email-change confirmations, anything that recovers an account.

    They must never be the same connection. A password reset for the platform
    owner routed through a customer's mail server would put account recovery for
    the whole platform behind infrastructure a customer controls.

    A single row. Stored in the database rather than the environment so changing
    provider is a form edit rather than a deploy - the console is where an
    operator already is when they discover mail is broken.
    """

    singleton_id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=255, blank=True)

    # Sealed with the same AES-256-GCM vault as provider credentials (D-071).
    # No serializer field and no endpoint returns it; the API can only report
    # whether one exists.
    smtp_password_ciphertext = models.TextField(blank=True, editable=False)

    smtp_use_tls = models.BooleanField(default=True)
    from_email = models.EmailField(blank=True, help_text="The From address on platform emails.")
    from_name = models.CharField(
        max_length=120,
        blank=True,
        default="MateAssist",
        help_text="Display name on platform emails.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "platform settings"

    def __str__(self) -> str:
        return f"platform mail via {self.smtp_host or 'unconfigured'}"

    @classmethod
    def load(cls) -> "PlatformSettings":
        """The one row, created on first read.

        get_or_create rather than a fixture: a fresh deployment must be able to
        open the settings page before anyone has saved anything.
        """
        instance, _ = cls.objects.get_or_create(singleton_id=1)
        return instance

    # ---- credential handling ---------------------------------------------

    @property
    def vault_context(self) -> str:
        return "platform-smtp"

    @property
    def is_configured(self) -> bool:
        """Enough to send. A host with no From address produces mail that
        arrives claiming to be from nobody."""
        return bool(self.smtp_host and self.from_email)

    def set_smtp_password(self, secret: str) -> None:
        from apps.ai import vault

        secret = (secret or "").strip()
        self.smtp_password_ciphertext = (
            vault.seal(secret, context=self.vault_context) if secret else ""
        )

    def reveal_smtp_password(self) -> str:
        from apps.ai import vault

        if not self.smtp_password_ciphertext:
            return ""
        return vault.open_sealed(self.smtp_password_ciphertext, context=self.vault_context)
