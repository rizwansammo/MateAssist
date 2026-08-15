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


RESERVED_LABELS = {"admin", "www", "api", "static", "media", "mail"}


def _subdomain(host: str) -> str | None:
    """The workspace slug in this host, or None for the platform surface.

    Resolved against BASE_DOMAIN rather than by counting labels (D-148).

    The original implementation took the first label and called it the slug.
    That is correct for `netamate.mateassist.site` and wrong for the apex:
    `mateassist.site` has two labels, so it read "mateassist" as a workspace,
    failed to find one, and returned 404 "Unknown workspace" for every request
    to the platform surface - including the platform owner's login.

    **Development could not catch this.** BASE_DOMAIN was `localhost:8000`, and
    `localhost` is a single label, so the length check returned None and the
    apex behaved correctly for the wrong reason. It only broke on a real domain,
    where the apex has two labels like any other host.

    An unrecognised host resolves to None rather than to a tenant, so a request
    that somehow reaches this app on the wrong domain gets the platform surface
    (which then refuses it) rather than a stranger's workspace.
    """
    from django.conf import settings

    hostname = host.split(":")[0].lower().rstrip(".")
    base = settings.BASE_DOMAIN.split(":")[0].lower().rstrip(".")

    if not base or hostname == base:
        return None

    suffix = f".{base}"
    if not hostname.endswith(suffix):
        return None

    label = hostname[: -len(suffix)]
    # Reject an empty label and any deeper nesting: `a.b.mateassist.site` is not
    # workspace "a.b", and treating it as one would let a slug contain a dot.
    if not label or "." in label:
        return None
    if label in RESERVED_LABELS:
        return None
    return label


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
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])
            return self.get_response(request)
