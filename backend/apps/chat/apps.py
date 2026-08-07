from django.apps import AppConfig


class ChatConfig(AppConfig):
    """Chat bounded context (Phase 6)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"
    label = "chat"
    verbose_name = "Chat"
