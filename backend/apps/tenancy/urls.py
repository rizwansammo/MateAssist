from django.urls import path

from .views import (
    WorkspaceMailTestView,
    WorkspaceSettingsView,
    WorkspaceUserListView,
    WorkspaceUserPasswordResetView,
)

app_name = "tenancy"

urlpatterns = [
    path("workspace/settings/", WorkspaceSettingsView.as_view(), name="workspace-settings"),
    path("workspace/mail-test/", WorkspaceMailTestView.as_view(), name="workspace-mail-test"),
    path("workspace/users/", WorkspaceUserListView.as_view(), name="workspace-users"),
    path(
        "workspace/users/<int:user_id>/reset-password/",
        WorkspaceUserPasswordResetView.as_view(),
        name="workspace-user-reset-password",
    ),
]
