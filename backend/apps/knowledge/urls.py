from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, DocumentViewSet

app_name = "knowledge"

router = DefaultRouter()
router.register("knowledge/documents", DocumentViewSet, basename="document")
router.register("knowledge/categories", CategoryViewSet, basename="category")

urlpatterns = router.urls
