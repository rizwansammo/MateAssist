"""Resolve the tenant from the Host header and arm RLS for the request (D-021).

The database session variable is set with set_config(..., is_local => true),
which is transaction-scoped - so the request is wrapped in an explicit
transaction to give the variable and the work the same lifetime. Without that,
the setting would leak across requests on a pooled connection.

Requests with no resolvable tenant (the admin host, health checks) simply leave
app.tenant_id unset. The RLS policy compares against NULL, which is never true,
so unset means "no rows" rather than "all rows".
"""

from django.db import connection, transaction
from django.http import JsonResponse

from .context import tenant_context
from .models import Tenant

TENANT_EXEMPT_PREFIXES = ("/api/v1/health", "/django-admin", "/api/schema", "/api/docs")


def _subdomain(host: str) -> str | None:
    hostname = host.split(":")[0].lower()
    labels = hostname.split(".")
    if len(labels) < 2:
        return None
    candidate = labels[0]
    if candidate in {"admin", "www", "api", "localhost", "127"}:
        return None
    return candidate


class SubdomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(TENANT_EXEMPT_PREFIXES):
            request.tenant = None
            return self.get_response(request)

        slug = _subdomain(request.get_host())
        tenant = None
        if slug:
            tenant = Tenant.objects.filter(slug=slug).first()
            if tenant is None:
                return JsonResponse({"detail": "Unknown workspace."}, status=404)
            # D-035: suspension blocks sign-in and pauses AI routing immediately.
            if not tenant.is_active:
                return JsonResponse({"detail": "This workspace is suspended."}, status=403)

        request.tenant = tenant

        if tenant is None:
            with tenant_context(None):
                return self.get_response(request)

        with transaction.atomic(), tenant_context(tenant.id):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)]
                )
            return self.get_response(request)
