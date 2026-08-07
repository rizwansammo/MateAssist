from rest_framework.routers import DefaultRouter

from .views import ModelPriceViewSet, ProviderKeyViewSet

app_name = "platformadmin"

router = DefaultRouter()
router.register("platform/keys", ProviderKeyViewSet, basename="providerkey")
router.register("platform/prices", ModelPriceViewSet, basename="modelprice")

urlpatterns = router.urls
