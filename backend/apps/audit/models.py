"""Append-only platform event log (D-114).

Metadata only - tenant payloads are never written here. An audit log that
contains the thing it is auditing is a second copy of the data to protect.
"""

from django.conf import settings
from django.db import models


class Level(models.TextChoices):
    INFO = "info", "Info"
    WARN = "warn", "Warn"
    ERROR = "error", "Error"
    AUTH = "auth", "Auth"


class AuditEvent(models.Model):
    # Nullable: platform-level events (vault rotation, tenant suspension) belong
    # to no workspace. RLS treats a null tenant as platform scope, exactly as it
    # does for Membership.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    action = models.CharField(max_length=64, db_index=True)
    target = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["tenant", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.created_at:%H:%M:%S} {self.level} {self.action}"


def record(action: str, *, tenant=None, actor=None, level=Level.INFO, target="", ip=None, **meta):
    """Write an audit event.

    Platform-scope events (tenant=None) are written through the `admin` alias.
    They legitimately have to be recorded while a tenant request is in flight -
    a Gemini key hitting its quota during one workspace's upload is platform
    infrastructure, not that workspace's data - and the RLS WITH CHECK clause
    correctly refuses a null-tenant row when a tenant context is active. Routing
    platform writes to the platform connection is the honest resolution;
    weakening the policy to let them through would not be.

    Never raises: an audit failure must not take down the operation it is
    describing. A dropped log line is bad; a 500 on a successful key rotation
    because the log write failed is worse.
    """
    alias = "default" if tenant is not None else "admin"
    try:
        return AuditEvent.objects.using(alias).create(
            tenant=tenant,
            actor=actor,
            level=level,
            action=action,
            target=str(target)[:128],
            metadata=meta,
            ip=ip,
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("audit write failed for action=%s", action)
        return None
