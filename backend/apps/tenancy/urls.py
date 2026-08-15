from django.urls import path

from .views import WorkspaceSettingsView

app_name = "tenancy"

urlpatterns = [
    path("workspace/settings/", WorkspaceSettingsView.as_view(), name="workspace-settings"),
]
