"""Platform-admin API: the credential vault surface (D-070 to D-075)."""

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ai.models import Engine, ModelPrice, ProviderKey
from apps.audit.models import Level, record

from .permissions import IsPlatformOwner
from .serializers import ModelPriceSerializer, ProviderKeySerializer, ProviderKeyWriteSerializer


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
                "engine": key.engine,
                "label": request.data.get("label", key.label),
            }
        )
        payload.is_valid(raise_exception=True)

        key.label = payload.validated_data["label"]
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
