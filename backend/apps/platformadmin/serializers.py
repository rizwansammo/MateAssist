"""Vault API serializers.

D-072: there is no field here that reads the credential. The plaintext is
write-only because no read path exists - not because a flag is set that could be
flipped or forgotten in a refactor. `test_no_serializer_field_exposes_the_plaintext`
fails the build if one ever appears.
"""

from rest_framework import serializers

from apps.ai.models import PROVIDER_DEFAULTS, Engine, ModelPrice, Provider, ProviderKey
from apps.tenancy.models import Tenant


class ProviderKeySerializer(serializers.ModelSerializer):
    """Read shape. Note the absence of `ciphertext`."""

    masked = serializers.CharField(read_only=True)
    is_available = serializers.SerializerMethodField()
    # Resolved values, so the operator sees what will ACTUALLY be called rather
    # than a blank field meaning "the default, whatever that is".
    resolved_model = serializers.CharField(read_only=True)
    resolved_base_url = serializers.CharField(read_only=True)

    class Meta:
        model = ProviderKey
        fields = (
            "id",
            "engine",
            "provider",
            "base_url",
            "model",
            "resolved_model",
            "resolved_base_url",
            "label",
            "masked",
            "last4",
            "status",
            "weight",
            "daily_quota",
            "requests_today",
            "cooldown_until",
            "created_at",
            "last_used_at",
            "is_available",
        )
        read_only_fields = fields

    def get_is_available(self, obj) -> bool:
        return obj.is_available()


class ProviderKeyWriteSerializer(serializers.Serializer):
    """Create or rotate. `secret` is write-only and never echoed back."""

    engine = serializers.ChoiceField(choices=Engine.choices)
    provider = serializers.ChoiceField(choices=Provider.choices, default=Provider.OPENAI_COMPATIBLE)
    base_url = serializers.CharField(required=False, allow_blank=True, default="")
    model = serializers.CharField(required=False, allow_blank=True, default="", max_length=64)
    label = serializers.CharField(max_length=64)
    secret = serializers.CharField(write_only=True, trim_whitespace=True)
    weight = serializers.IntegerField(default=1, min_value=1, max_value=100)
    daily_quota = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate_secret(self, value: str) -> str:
        value = value.strip()
        if len(value) < 8:
            raise serializers.ValidationError("That does not look like a provider credential.")
        return value

    def validate(self, attrs):
        """A generic endpoint has no defaults to fall back on.

        Catching it here means the operator sees a form error instead of a key
        that saves cleanly and then fails on the first real request.
        """
        provider = attrs.get("provider")
        defaults = PROVIDER_DEFAULTS.get(provider, {})

        if not attrs.get("base_url") and not defaults.get("base_url"):
            raise serializers.ValidationError(
                {"base_url": "A base URL is required for a generic OpenAI-compatible endpoint."}
            )

        engine = attrs.get("engine")
        default_model = defaults.get("vision_model" if engine == Engine.VISION else "text_model")
        if not attrs.get("model") and not default_model:
            raise serializers.ValidationError(
                {"model": f"A model id is required - {provider} has no default for {engine}."}
            )
        return attrs


class TenantSerializer(serializers.ModelSerializer):
    """The workspace registry, for the platform Tenants screen.

    Counts are annotated by the viewset on the RLS-bypassing connection - a
    per-row `.count()` here would be one query per tenant, and would return zero
    anyway, since a tenant-scoped related manager reads a ContextVar the platform
    surface never sets.
    """

    # Sourced from the viewset's annotations, which are deliberately named
    # `*_count` because `documents` is already Tenant's reverse accessor for
    # Document and annotating over it fails at query-build time.
    users = serializers.IntegerField(source="user_count", read_only=True)
    documents = serializers.IntegerField(source="document_count", read_only=True)
    subdomain = serializers.CharField(read_only=True)

    class Meta:
        model = Tenant
        fields = (
            "id",
            "name",
            "slug",
            "subdomain",
            "plan",
            "region",
            "status",
            "support_email",
            "users",
            "documents",
            "created_at",
        )
        read_only_fields = ("id", "slug", "subdomain", "users", "documents", "created_at")


class ModelPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelPrice
        fields = (
            "id",
            "engine",
            "model",
            "input_per_1m",
            "output_per_1m",
            "per_image",
            "currency",
            "effective_from",
        )
