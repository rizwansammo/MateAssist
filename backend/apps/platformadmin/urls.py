from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AuditLogView,
    ModelPriceViewSet,
    PlatformTenantSpendView,
    PlatformUsageView,
    ProviderKeyViewSet,
    TenantBudgetViewSet,
)

app_name = "platformadmin"

router = DefaultRouter()
router.register("platform/keys", ProviderKeyViewSet, basename="providerkey")
router.register("platform/prices", ModelPriceViewSet, basename="modelprice")
router.register("platform/budgets", TenantBudgetViewSet, basename="tenantbudget")

urlpatterns = router.urls + [
    path("platform/usage/", PlatformUsageView.as_view(), name="platform-usage"),
    path("platform/spend/", PlatformTenantSpendView.as_view(), name="platform-spend"),
    path("platform/logs/", AuditLogView.as_view(), name="platform-logs"),
]
