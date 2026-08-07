from django.apps import AppConfig


class PlatformAdminConfig(AppConfig):
    """Platform Admin bounded context (Phase 4)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platformadmin"
    label = "platformadmin"
    verbose_name = "Platform Admin"
