"""Serializers for the usage and budget surfaces."""

from rest_framework import serializers

from .models import TenantBudget


class TenantBudgetSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    tenant_slug = serializers.SlugField(source="tenant.slug", read_only=True)
    is_capped = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantBudget
        fields = [
            "id",
            "tenant",
            "tenant_name",
            "tenant_slug",
            "monthly_usd",
            "enforce",
            "alert_at_percent",
            "is_capped",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]

    def validate_monthly_usd(self, value):
        if value < 0:
            raise serializers.ValidationError("A budget cannot be negative.")
        return value

    def validate_alert_at_percent(self, value):
        if not 1 <= value <= 100:
            raise serializers.ValidationError("Alert threshold must be between 1 and 100.")
        return value


class AuditEventSerializer(serializers.Serializer):
    """Read-only projection of an AuditEvent.

    A Serializer rather than a ModelSerializer because this log is append-only
    (D-114) - there is no write path to generate, and offering one would be
    misleading. `metadata` is already free of tenant payloads by construction.
    """

    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    level = serializers.CharField(read_only=True)
    action = serializers.CharField(read_only=True)
    target = serializers.CharField(read_only=True)
    metadata = serializers.JSONField(read_only=True)
    ip = serializers.IPAddressField(read_only=True)
    tenant_id = serializers.IntegerField(read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True, default=None)
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)
