"""Platform-admin API: the credential vault surface (D-070 to D-075) and the
cross-tenant reporting surface (D-112, D-114).

Everything here is gated by `IsPlatformOwner`, and the reporting views
additionally read on the RLS-bypassing `admin` connection. That combination -
superuser connection plus platform-owner check - is the only path in the system
that can observe more than one workspace, so it lives in one module rather than
being spread across the apps it reports on.
"""

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.models import Engine, ModelPrice, ProviderKey
from apps.audit.models import AuditEvent, Level, record
from apps.metering import rollups
from apps.metering.models import TenantBudget
from apps.metering.serializers import AuditEventSerializer, TenantBudgetSerializer
from apps.tenancy.models import Tenant

from .permissions import IsPlatformOwner
from .serializers import (
    ModelPriceSerializer,
    ProviderKeySerializer,
    ProviderKeyWriteSerializer,
    TenantSerializer,
)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")


class ProviderKeyViewSet(viewsets.ModelViewSet):
    queryset = ProviderKey.objects.all()
    serializer_class = ProviderKeySerializer
    permission_classes = [IsPlatformOwner]
    http_method_names = ["get", "post", "delete"]  # rotation is an explicit action

    def get_queryset(self):
        queryset = super().get_queryset()
        engine = self.request.query_params.get("engine")
        if engine in dict(Engine.choices):
            queryset = queryset.filter(engine=engine)
        return queryset

    @extend_schema(request=ProviderKeyWriteSerializer, responses={201: ProviderKeySerializer})
    def create(self, request, *args, **kwargs):
        payload = ProviderKeyWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        key = ProviderKey(
            engine=data["engine"],
            provider=data["provider"],
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            label=data["label"],
            weight=data["weight"],
            daily_quota=data.get("daily_quota"),
            created_by=request.user,
        )
        # Sealed before the row is written; the plaintext never touches the ORM.
        key.set_secret(data["secret"])
        key.save()

        record(
            "vault.create",
            actor=request.user,
            level=Level.AUTH,
            target=str(key),
            ip=_client_ip(request),
            engine=key.engine,
            label=key.label,
            last4=key.last4,
        )
        return Response(ProviderKeySerializer(key).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ProviderKeyWriteSerializer, responses={200: ProviderKeySerializer})
    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        key = self.get_object()
        payload = ProviderKeyWriteSerializer(
            data={
                **request.data,
                # The role is fixed by the key being rotated; only the credential
                # and its provider configuration may change.
                "engine": key.engine,
                "provider": request.data.get("provider", key.provider),
                "label": request.data.get("label", key.label),
            }
        )
        payload.is_valid(raise_exception=True)

        key.label = payload.validated_data["label"]
        key.provider = payload.validated_data["provider"]
        key.base_url = payload.validated_data.get("base_url", "")
        key.model = payload.validated_data.get("model", "")
        key.set_secret(payload.validated_data["secret"])
        key.status = ProviderKey.Status.ACTIVE
        key.cooldown_until = None
        key.requests_today = 0
        key.save()

        record(
            "vault.rotate",
            actor=request.user,
            level=Level.AUTH,
            target=str(key),
            ip=_client_ip(request),
            engine=key.engine,
            label=key.label,
            last4=key.last4,
        )
        return Response(ProviderKeySerializer(key).data)

    @extend_schema(responses={200: ProviderKeySerializer})
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        key = self.get_object()
        key.status = ProviderKey.Status.REVOKED
        key.requests_today = 0
        key.cooldown_until = None
        key.save(update_fields=["status", "requests_today", "cooldown_until"])

        record(
            "vault.revoke",
            actor=request.user,
            level=Level.AUTH,
            target=str(key),
            ip=_client_ip(request),
            engine=key.engine,
            label=key.label,
        )
        return Response(ProviderKeySerializer(key).data)

    def destroy(self, request, *args, **kwargs):
        """Purge. Only a revoked key can be deleted, so a live credential cannot
        vanish from the pool by accident."""
        key = self.get_object()
        if key.status != ProviderKey.Status.REVOKED:
            return Response(
                {"detail": "Revoke the key before purging it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        label, engine = key.label, key.engine
        key.delete()
        record(
            "vault.purge",
            actor=request.user,
            level=Level.AUTH,
            target=f"{engine}:{label}",
            ip=_client_ip(request),
            engine=engine,
            label=label,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def pool_status(self, request):
        """Per-engine health, for the AI Configuration screen."""
        now = timezone.now()
        summary = {}
        for value, _label in Engine.choices:
            keys = list(ProviderKey.objects.filter(engine=value))
            live = [k for k in keys if k.status != ProviderKey.Status.REVOKED]
            summary[value] = {
                "total": len(keys),
                "pool": len(live),
                "active": sum(1 for k in live if k.is_available(now)),
                "rate_limited": sum(1 for k in live if k.status == ProviderKey.Status.RATE_LIMITED),
                "usable": any(k.is_available(now) for k in live),
            }
        return Response(summary)


class ModelPriceViewSet(viewsets.ModelViewSet):
    """Rates live in the database and are editable here (D-111)."""

    queryset = ModelPrice.objects.all()
    serializer_class = ModelPriceSerializer
    permission_classes = [IsPlatformOwner]


class TenantViewSet(viewsets.ModelViewSet):
    """The workspace registry (D-020).

    `Tenant` is not itself RLS-protected - it is the registry, not tenant data -
    but the *counts* are: memberships and documents are tenant-owned, so
    annotating them requires the platform connection. On `default` with no tenant
    armed every count would come back zero, which is the same silent-wrong-number
    failure that `month_to_date_cost` had.
    """

    serializer_class = TenantSerializer
    permission_classes = [IsPlatformOwner]
    http_method_names = ["get", "post", "patch"]  # suspension is an explicit action

    def get_queryset(self):
        # Annotation names must not collide with the reverse accessors they
        # count. `TenantScopedModel` sets related_name="%(class)ss", so Document
        # already occupies `documents` on Tenant, and annotating over it raises
        # at query-build time - a 500 on every request to this endpoint.
        return (
            Tenant.objects.using(rollups.PLATFORM_ALIAS)
            .annotate(
                user_count=Count("memberships", distinct=True),
                document_count=Count("documents", distinct=True),
            )
            .order_by("name")
        )

    @extend_schema(responses={200: TenantSerializer})
    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        """Blocks sign-in and pauses AI routing for the workspace."""
        return self._set_status(request, Tenant.Status.SUSPENDED, "tenant.suspend", Level.WARN)

    @extend_schema(responses={200: TenantSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self._set_status(request, Tenant.Status.ACTIVE, "tenant.activate", Level.INFO)

    def _set_status(self, request, status_value, action_name, level):
        tenant = self.get_object()
        tenant.status = status_value
        tenant.save(using=rollups.PLATFORM_ALIAS, update_fields=["status"])
        record(
            action_name,
            actor=request.user,
            level=level,
            target=tenant.name,
            ip=_client_ip(request),
            slug=tenant.slug,
        )
        return Response(self.get_serializer(tenant).data)


# ------------------------------------------------- cross-tenant reporting ----

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
    if days is not None:
        days = max(1, min(days, 365))
    return rollups.window(days)


class PlatformUsageView(APIView):
    """Aggregate usage across every workspace - the Overview screen.

    Reads on the `admin` connection, which bypasses RLS. `IsPlatformOwner` is
    therefore the only thing standing between this response and every tenant's
    volume figures, and it checks the database rather than a token claim so that
    revoking the role takes effect immediately.
    """

    permission_classes = [IsPlatformOwner]

    @extend_schema(parameters=[WINDOW_PARAM], responses={200: dict})
    def get(self, request):
        since, until = _window(request)
        return Response(
            {
                "window": {"since": since.isoformat(), "until": until.isoformat()},
                "totals": rollups.platform_summary(since=since, until=until).as_dict(),
                "by_engine": rollups.platform_by_engine(since=since, until=until),
                "by_model": rollups.platform_by_model(since=since, until=until),
                "series": rollups.platform_series(since=since, until=until),
            }
        )


class PlatformTenantSpendView(APIView):
    """Per-workspace spend - the Billing screen's table."""

    permission_classes = [IsPlatformOwner]

    @extend_schema(parameters=[WINDOW_PARAM], responses={200: dict})
    def get(self, request):
        since, until = _window(request)
        rows = rollups.platform_by_tenant(since=since, until=until)
        totals = rollups.platform_summary(since=since, until=until)
        return Response(
            {
                "window": {"since": since.isoformat(), "until": until.isoformat()},
                "tenants": rows,
                "totals": totals.as_dict(),
            }
        )


class AuditLogView(APIView):
    """The System Logs screen (D-114).

    Append-only and read-only. Filterable by level, action prefix and tenant;
    paginated by explicit limit/offset rather than a paginator class because the
    queryset spans connections and the response shape is fixed by the UI.
    """

    permission_classes = [IsPlatformOwner]

    @extend_schema(
        parameters=[
            OpenApiParameter("level", str, description="info | warn | error | auth"),
            OpenApiParameter("action", str, description="Prefix match, e.g. 'vault.'"),
            OpenApiParameter("tenant", int, description="Filter to one workspace."),
            OpenApiParameter("limit", int),
            OpenApiParameter("offset", int),
        ],
        responses={200: dict},
    )
    def get(self, request):
        # Platform alias: the log deliberately spans workspaces, and platform-scope
        # rows carry a null tenant that the RLS predicate would otherwise hide
        # whenever a tenant context happened to be armed.
        queryset = AuditEvent.objects.using(rollups.PLATFORM_ALIAS).select_related(
            "tenant", "actor"
        )

        level = request.query_params.get("level")
        if level in dict(Level.choices):
            queryset = queryset.filter(level=level)

        action_prefix = request.query_params.get("action")
        if action_prefix:
            queryset = queryset.filter(action__startswith=action_prefix)

        tenant_id = request.query_params.get("tenant")
        if tenant_id and tenant_id.isdigit():
            queryset = queryset.filter(tenant_id=int(tenant_id))

        try:
            limit = min(max(int(request.query_params.get("limit", 50)), 1), 200)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            limit, offset = 50, 0

        total = queryset.count()
        page = queryset[offset : offset + limit]

        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "results": AuditEventSerializer(page, many=True).data,
            }
        )


class TenantBudgetViewSet(viewsets.ModelViewSet):
    """Monthly spend caps (D-113).

    Platform-owner only. A workspace cannot see, create or raise its own cap -
    that is the entire point of keeping `TenantBudget` off the tenant-scoped
    base class.
    """

    serializer_class = TenantBudgetSerializer
    permission_classes = [IsPlatformOwner]

    def get_queryset(self):
        return TenantBudget.objects.using(rollups.PLATFORM_ALIAS).select_related("tenant")

    def _audit(self, budget, action):
        record(
            action,
            actor=self.request.user,
            level=Level.INFO,
            target=str(budget.tenant),
            ip=_client_ip(self.request),
            monthly_usd=str(budget.monthly_usd),
            enforce=budget.enforce,
        )

    def perform_create(self, serializer):
        budget = serializer.save()
        self._audit(budget, "budget.create")

    def perform_update(self, serializer):
        budget = serializer.save()
        self._audit(budget, "budget.update")

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        """Cap, month-to-date spend and whether the workspace is over it."""
        from apps.metering import budgets as budget_api

        budget = self.get_object()
        # Platform alias: no tenant context is armed on this surface, so the
        # default connection would report zero spend for every workspace.
        return Response(budget_api.status_for(budget.tenant, alias=rollups.PLATFORM_ALIAS))
