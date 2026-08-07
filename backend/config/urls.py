"""Root URL configuration.

Everything the SPAs consume lives under /api/v1/. The version prefix is in the
path from the first endpoint so a v2 can coexist rather than break clients.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.accounts.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("django-admin/", admin.site.urls),
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
    ]
