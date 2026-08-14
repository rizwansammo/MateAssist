from django.urls import path

from .views import UsageSeriesView, UsageSummaryView

app_name = "metering"

# No `usage/by-model/` route: see the note in views.py (D-136). A workspace sees
# its usage by engine ROLE, never by model identifier.
urlpatterns = [
    path("usage/summary/", UsageSummaryView.as_view(), name="usage-summary"),
    path("usage/series/", UsageSeriesView.as_view(), name="usage-series"),
]
