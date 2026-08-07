from django.apps import AppConfig


class AiConfig(AppConfig):
    """AI Engines bounded context (Phase 4)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = "AI Engines"
