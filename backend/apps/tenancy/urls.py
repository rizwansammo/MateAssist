from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AssistantRuleViewSet,
    WorkspaceMailTestView,
    WorkspaceSettingsView,
    WorkspaceUserListView,
    WorkspaceUserPasswordResetView,
)

app_name = "tenancy"

router = DefaultRouter()
router.register("workspace/rules", AssistantRuleViewSet, basename="assistantrule")

urlpatterns = router.urls + [
    path("workspace/settings/", WorkspaceSettingsView.as_view(), name="workspace-settings"),
    path("workspace/mail-test/", WorkspaceMailTestView.as_view(), name="workspace-mail-test"),
    path("workspace/users/", WorkspaceUserListView.as_view(), name="workspace-users"),
    path(
        "workspace/users/<int:user_id>/reset-password/",
        WorkspaceUserPasswordResetView.as_view(),
        name="workspace-user-reset-password",
    ),
]
