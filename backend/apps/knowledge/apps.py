from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    """Knowledge Base bounded context (Phase 5)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
    label = "knowledge"
    verbose_name = "Knowledge Base"
