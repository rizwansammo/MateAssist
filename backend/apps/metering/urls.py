from django.urls import path

from .views import UsageByModelView, UsageSeriesView, UsageSummaryView

app_name = "metering"

urlpatterns = [
    path("usage/summary/", UsageSummaryView.as_view(), name="usage-summary"),
    path("usage/series/", UsageSeriesView.as_view(), name="usage-series"),
    path("usage/by-model/", UsageByModelView.as_view(), name="usage-by-model"),
]
