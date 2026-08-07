from django.apps import AppConfig


class HelpdeskConfig(AppConfig):
    """Helpdesk bounded context (Phase 3)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.helpdesk"
    label = "helpdesk"
    verbose_name = "Helpdesk"
