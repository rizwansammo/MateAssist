from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Audit bounded context (Phase 7)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Audit"
