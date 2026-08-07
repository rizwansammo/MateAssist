from django.apps import AppConfig


class MeteringConfig(AppConfig):
    """Metering bounded context (Phase 7)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.metering"
    label = "metering"
    verbose_name = "Metering"
