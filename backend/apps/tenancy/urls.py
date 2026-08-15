from django.urls import path

from .views import WorkspaceMailTestView, WorkspaceSettingsView

app_name = "tenancy"

urlpatterns = [
    path("workspace/settings/", WorkspaceSettingsView.as_view(), name="workspace-settings"),
    path("workspace/mail-test/", WorkspaceMailTestView.as_view(), name="workspace-mail-test"),
]
