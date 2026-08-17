from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AuditLogView,
    BillingRateViewSet,
    BillingStatementView,
    ModelPriceViewSet,
    PlatformMailTestView,
    PlatformMailView,
    PlatformTenantSpendView,
    PlatformUsageView,
    ProviderKeyViewSet,
    TenantBudgetViewSet,
    TenantViewSet,
)

app_name = "platformadmin"

router = DefaultRouter()
router.register("platform/keys", ProviderKeyViewSet, basename="providerkey")
router.register("platform/prices", ModelPriceViewSet, basename="modelprice")
router.register("platform/billing-rates", BillingRateViewSet, basename="billingrate")
router.register("platform/budgets", TenantBudgetViewSet, basename="tenantbudget")
router.register("platform/tenants", TenantViewSet, basename="platformtenant")

urlpatterns = router.urls + [
    path("platform/usage/", PlatformUsageView.as_view(), name="platform-usage"),
    path("platform/spend/", PlatformTenantSpendView.as_view(), name="platform-spend"),
    path("platform/logs/", AuditLogView.as_view(), name="platform-logs"),
    path("platform/mail/", PlatformMailView.as_view(), name="platform-mail"),
    path("platform/mail-test/", PlatformMailTestView.as_view(), name="platform-mail-test"),
    path("platform/statements/", BillingStatementView.as_view(), name="platform-statements"),
]
