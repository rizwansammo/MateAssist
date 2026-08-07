from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.tenancy.models import Membership, Role


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    job_title = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    initials = serializers.CharField(read_only=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        request = self.context["request"]
        tenant = getattr(request, "tenant", None)

        user = authenticate(
            request, username=attrs["email"].lower().strip(), password=attrs["password"]
        )
        # One message for every failure mode. Distinguishing "no such user" from
        # "wrong password" from "not a member here" turns the login form into a
        # membership oracle for enumerating a workspace's staff.
        invalid = serializers.ValidationError({"detail": "Invalid credentials."})

        if user is None or not user.is_active:
            raise invalid

        if tenant is None:
            # Platform surface: only a PLATFORM_OWNER may sign in without a tenant.
            membership = Membership.all_objects.filter(
                user=user, tenant__isnull=True, role=Role.PLATFORM_OWNER
            ).first()
        else:
            # D-034: credentials are validated against the tenant resolved from
            # the subdomain, so the same account in two workspaces is two
            # separate memberships and neither implies the other.
            membership = Membership.all_objects.filter(user=user, tenant=tenant).first()

        if membership is None:
            raise invalid

        attrs["user"] = user
        attrs["membership"] = membership
        return attrs


class SessionSerializer(serializers.Serializer):
    """What the SPA gets after a successful login or refresh."""

    access = serializers.CharField()
    user = UserSerializer()
    role = serializers.CharField()
    tenant = serializers.SerializerMethodField()

    def get_tenant(self, obj):
        tenant = obj.get("tenant")
        if tenant is None:
            return None
        return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "plan": tenant.plan}
