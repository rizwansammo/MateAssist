from django.apps import AppConfig


class TenancyConfig(AppConfig):
    """Tenancy bounded context (Phase 2)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenancy"
    label = "tenancy"
    verbose_name = "Tenancy"
