"""Platform-admin API: the credential vault surface (D-070 to D-075) and the
cross-tenant reporting surface (D-112, D-114).

Everything here is gated by `IsPlatformOwner`, and the reporting views
additionally read on the RLS-bypassing `admin` connection. That combination -
superuser connection plus platform-owner check - is the only path in the system
that can observe more than one workspace, so it lives in one module rather than
being spread across the apps it reports on.
"""

from decimal import Decimal

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.models import Engine, ModelPrice, ProviderKey
from apps.ai.probe import check_key
from apps.audit.models import AuditEvent, Level, record
from apps.metering import billing, rollups
from apps.metering.models import BillingRate, TenantBudget
from apps.metering.serializers import AuditEventSerializer, TenantBudgetSerializer
from apps.tenancy import provisioning
from apps.tenancy.models import Tenant

from . import mail as platform_mail
from .models import PlatformSettings
from .permissions import IsPlatformOwner
from .serializers import (
    BillingRateSerializer,
    ModelPriceSerializer,
    PlatformMailSerializer,
    ProviderKeyCheckSerializer,
    ProviderKeyConfigSerializer,
    ProviderKeySerializer,
    ProviderKeyWriteSerializer,
    TenantSerializer,
    WorkspaceCreateSerializer,
)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")


class ProviderKeyViewSet(viewsets.ModelViewSet):
    queryset = ProviderKey.objects.all()
    serializer_class = ProviderKeySerializer
    permission_classes = [IsPlatformOwner]
    # PATCH edits configuration only. Replacing the credential stays on the
    # explicit rotate action, so "fix the model id" can never become "overwrite
    # the key" by accident, and the audit log says which one happened (D-155).
    http_method_names = ["get", "post", "patch", "delete"]

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

    @extend_schema(request=ProviderKeyConfigSerializer, responses={200: ProviderKeySerializer})
    def partial_update(self, request, *args, **kwargs):
        """Change a key's configuration in place.

        Exists because providers retire model ids. Without it the only way to
        point at a working model was deleting the key and re-entering the
        credential - friction that ends with an operator leaving it broken.
        """
        key = self.get_object()
        payload = ProviderKeyConfigSerializer(data=request.data, context={"key": key})
        payload.is_valid(raise_exception=True)
        changes = payload.validated_data

        before = {field: getattr(key, field) for field in changes}

        # The label is part of the vault's additional authenticated data
        # (`providerkey:{engine}:{label}`), so renaming a key would leave its
        # ciphertext undecryptable forever - a silent, unrecoverable loss of a
        # credential nobody could read back to re-enter. Unseal under the old
        # context and re-seal under the new one, in that order.
        renaming = "label" in changes and changes["label"] != key.label
        secret = key.reveal() if renaming else None

        for field, value in changes.items():
            setattr(key, field, value)

        if renaming:
            key.set_secret(secret)

        # A key parked in cooldown or rate-limited is usually parked BECAUSE of
        # the setting just corrected, so an edit clears that state. Revoked is
        # left alone: that was a deliberate act and undoing it silently would
        # bring a retired credential back to life.
        if key.status == ProviderKey.Status.RATE_LIMITED:
            key.status = ProviderKey.Status.ACTIVE
        key.cooldown_until = None
        key.save()

        record(
            "vault.reconfigure",
            actor=request.user,
            level=Level.AUTH,
            target=str(key),
            ip=_client_ip(request),
            engine=key.engine,
            label=key.label,
            # What changed, never the credential - it cannot change on this path.
            changed=sorted(changes),
            before={k: str(v) for k, v in before.items()},
            after={k: str(v) for k, v in changes.items()},
        )
        return Response(ProviderKeySerializer(key).data)

    @extend_schema(responses={200: ProviderKeyCheckSerializer})
    @action(detail=True, methods=["post"])
    def check(self, request, pk=None):
        """Prove the key works with one real provider call (D-155).

        A saved key proves nothing: the credential can be valid while the model
        id is retired. Returns 200 either way - a working endpoint correctly
        reporting a broken configuration is not itself an error, and an HTTP
        failure code here would be indistinguishable from the request failing.
        """
        key = self.get_object()
        result = check_key(key)

        record(
            "vault.check",
            actor=request.user,
            level=Level.AUTH,
            target=str(key),
            ip=_client_ip(request),
            engine=key.engine,
            label=key.label,
            ok=result["ok"],
            detail=result["detail"][:200],
        )
        return Response(result)

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

    @extend_schema(request=WorkspaceCreateSerializer, responses={201: TenantSerializer})
    def create(self, request, *args, **kwargs):
        """Create the workspace AND its first administrator (D-173).

        Both or neither: a workspace with no administrator cannot be signed into
        and shows up in nobody's list, so a half-create leaves a row that only
        the database knows about.
        """
        payload = WorkspaceCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            result = provisioning.create_workspace(**payload.validated_data)
        except provisioning.ProvisioningError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        tenant, owner = result["tenant"], result["owner"]
        record(
            "tenant.created",
            actor=request.user,
            level=Level.AUTH,
            target=tenant.name,
            ip=_client_ip(request),
            slug=tenant.slug,
            owner=owner.email,
        )

        # Serialised from the object just created, not re-read through
        # get_queryset(). That queryset runs on the platform alias - a separate
        # connection - which cannot see a row this request has not committed.
        # The counts are known anyway for a workspace one second old.
        tenant.user_count = 1
        tenant.document_count = 0
        body = TenantSerializer(tenant).data
        # Returned once, like every other generated credential here. Nothing can
        # show it again, so the operator has to pass it on now.
        body["owner_email"] = owner.email
        body["owner_password"] = result["password"]
        return Response(body, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="reset-owner-password")
    def reset_owner_password(self, request, pk=None):
        """Reset the workspace owner's password.

        The platform owner sits above every workspace, so this needs no guard
        against privilege escalation - unlike the tenant-admin equivalent, which
        must refuse to touch a platform owner's shared User row (D-159).
        """
        tenant = self.get_object()
        if tenant.owner_id is None:
            return Response(
                {"detail": "This workspace has no owner on record."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        owner = tenant.owner
        password = request.data.get("new_password") or provisioning.generate_password()
        try:
            provisioning.check_password_strength(password, owner)
        except provisioning.ProvisioningError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        owner.set_password(password)
        owner.save(update_fields=["password"])

        record(
            "tenant.owner_password_reset",
            actor=request.user,
            level=Level.AUTH,
            target=owner.email,
            ip=_client_ip(request),
            tenant_scope=tenant.name,
        )
        return Response({"email": owner.email, "password": password})

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
                # Platform scope is the one place model identifiers are shown
                # (D-136) - an operator choosing rates needs to know what to
                # price.
                "totals": rollups.platform_summary(since=since, until=until).as_dict(
                    include_model_names=True
                ),
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
                "totals": totals.as_dict(include_model_names=True),
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


class BillingRateViewSet(viewsets.ModelViewSet):
    """Sell rates: the platform default, plus per-workspace overrides (D-160).

    Full CRUD deliberately, unlike provider keys. A rate carries no secret, and
    a mistyped price that cannot be corrected is worse than one that can.
    """

    queryset = BillingRate.objects.select_related("tenant").all()
    serializer_class = BillingRateSerializer
    permission_classes = [IsPlatformOwner]

    def perform_create(self, serializer):
        rate = serializer.save()
        record(
            "billing.rate.set",
            actor=self.request.user,
            target=str(rate),
            ip=_client_ip(self.request),
            tenant_scope=rate.tenant.name if rate.tenant_id else "platform default",
        )


class BillingStatementView(APIView):
    """What each workspace owes for a month (D-160).

    Derived, never stored. A stored invoice is a second copy of the truth that
    starts drifting from the usage table the moment either is corrected;
    recomputing from events means the figure always reflects what actually
    happened.
    """

    permission_classes = [IsPlatformOwner]

    @extend_schema(
        parameters=[
            OpenApiParameter("month", str, description="YYYY-MM. Defaults to the current month."),
            OpenApiParameter("tenant", int, description="One workspace instead of all."),
        ]
    )
    def get(self, request):
        today = timezone.localdate()
        raw = request.query_params.get("month", "")
        try:
            year, month = (
                (int(part) for part in raw.split("-", 1))
                if raw
                else (
                    today.year,
                    today.month,
                )
            )
            if not 1 <= month <= 12:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "month must look like 2026-08."}, status=status.HTTP_400_BAD_REQUEST
            )

        # The platform alias: statements span every workspace, and the default
        # connection under RLS would return one tenant's usage or none at all.
        tenants = Tenant.objects.using(rollups.PLATFORM_ALIAS).order_by("name")
        if request.query_params.get("tenant"):
            tenants = tenants.filter(pk=request.query_params["tenant"])

        rows = billing.statements(list(tenants), year=year, month=month)
        return Response(
            {
                "period": f"{year:04d}-{month:02d}",
                "total": str(sum((Decimal(row.get("total", "0")) for row in rows), Decimal("0"))),
                "statements": rows,
            }
        )


class PlatformMailView(APIView):
    """How MateAssist itself sends email (D-175).

    Not the same thing as a workspace's SMTP. This carries password reset codes
    and account emails, so it must never route through a customer's server -
    recovery for the platform cannot depend on a customer's infrastructure.
    """

    permission_classes = [IsPlatformOwner]

    @extend_schema(responses={200: PlatformMailSerializer})
    def get(self, request):
        return Response(PlatformMailSerializer(PlatformSettings.load()).data)

    @extend_schema(request=PlatformMailSerializer, responses={200: PlatformMailSerializer})
    def patch(self, request):
        config = PlatformSettings.load()
        serializer = PlatformMailSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        record(
            "platform.mail_updated",
            actor=request.user,
            level=Level.AUTH,
            target=config.smtp_host or "unconfigured",
            ip=_client_ip(request),
        )
        return Response(serializer.data)


class PlatformMailTestView(APIView):
    """Prove the settings work before anything depends on them.

    Without this the first real test of platform mail is a locked-out owner
    waiting for a reset code that was never going to arrive.
    """

    permission_classes = [IsPlatformOwner]

    @extend_schema(request=None, responses={200: dict})
    def post(self, request):
        recipient = (request.data.get("to") or request.user.email or "").strip()
        if not recipient:
            return Response(
                {"detail": "No address to send to."}, status=status.HTTP_400_BAD_REQUEST
            )

        result = platform_mail.send(
            to=recipient, subject=platform_mail.TEST_SUBJECT, body=platform_mail.TEST_BODY
        )
        record(
            "platform.mail_test",
            actor=request.user,
            level=Level.AUTH,
            target=recipient,
            ip=_client_ip(request),
            ok=result["sent"],
            detail=result["detail"][:200],
        )
        # 200 either way: a working endpoint correctly reporting broken mail is
        # not itself an error, and an HTTP failure here is indistinguishable
        # from the request failing.
        return Response(result)
