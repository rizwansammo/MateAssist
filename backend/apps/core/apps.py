from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Cross-cutting infrastructure: health, shared utilities, base migrations."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Core"
