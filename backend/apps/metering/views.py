"""Tenant-scoped usage API (D-112).

What a workspace can see about itself. Runs on the `default` connection as the
NOSUPERUSER app role, so RLS is live: even a mistake in these filters cannot
return another workspace's rows.

Platform-wide figures live in `apps.platformadmin.views` and are gated
separately - the two are kept in different modules precisely so that "can this
cross tenants?" is answerable from the import path.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenancy.models import Membership, Role

from . import budgets, rollups


class IsWorkspaceAdmin(BasePermission):
    """Stricter than knowledge's IsTenantAdmin, on purpose.

    That one allows any authenticated member to read, because runbooks are for
    everyone. Spend is not: an end user has no reason to see what their
    workspace costs, and volume figures leak how the business is being run. So
    reads are administrator-only here, with no method exemption.
    """

    message = "Only a workspace administrator can view usage and spend."

    def has_permission(self, request, view) -> bool:
        tenant = getattr(request, "tenant", None)
        if tenant is None or not request.user or not request.user.is_authenticated:
            return False
        return Membership.all_objects.filter(
            user=request.user, tenant=tenant, role=Role.TENANT_ADMIN
        ).exists()


WINDOW_PARAM = OpenApiParameter(
    name="days",
    description="Trailing window in days. Omit for the current billing month.",
    required=False,
    type=int,
)


def _window(request):
    raw = request.query_params.get("days")
    try:
        days = int(raw) if raw else None
    except ValueError:
        days = None
    # A negative or absurd window is a client bug; clamp rather than 400, since
    # a dashboard that errors on a bad query string is worse than one that shows
    # a sane default.
    if days is not None:
        days = max(1, min(days, 365))
    return rollups.window(days)


class UsageSummaryView(APIView):
    """Headline figures for the workspace dashboard."""

    permission_classes = [IsAuthenticated, IsWorkspaceAdmin]

    @extend_schema(parameters=[WINDOW_PARAM], responses={200: dict})
    def get(self, request):
        since, until = _window(request)
        tenant = request.tenant
        return Response(
            {
                "window": {"since": since.isoformat(), "until": until.isoformat()},
                "totals": rollups.tenant_summary(tenant, since=since, until=until).as_dict(),
                "by_engine": rollups.tenant_by_engine(tenant, since=since, until=until),
                "by_operation": rollups.tenant_by_operation(tenant, since=since, until=until),
                "budget": budgets.status_for(tenant),
            }
        )


class UsageSeriesView(APIView):
    """Daily buckets for the dashboard chart."""

    permission_classes = [IsAuthenticated, IsWorkspaceAdmin]

    @extend_schema(parameters=[WINDOW_PARAM], responses={200: dict})
    def get(self, request):
        since, until = _window(request)
        return Response(
            {
                "window": {"since": since.isoformat(), "until": until.isoformat()},
                "series": rollups.tenant_series(request.tenant, since=since, until=until),
            }
        )


# There is deliberately no tenant-facing by-model endpoint (D-136).
#
# Phase 7A shipped one. It listed `gemini-flash-latest` and `gemini-3.6-flash`
# to any workspace administrator, which names the vendor as clearly as a logo
# would. A workspace sees its consumption broken down by ROLE - "Text &
# reasoning", "Vision & OCR" - because that is what it is buying. Which company
# serves the role is platform configuration, disclosed in the contract rather
# than in a usage table.
#
# `rollups.tenant_by_model` still exists for platform-side reporting.
