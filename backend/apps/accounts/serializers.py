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


class AccountUpdateSerializer(serializers.Serializer):
    """Editing your own profile (D-158).

    The email address is the login identity, so changing it changes how the
    person signs in. It is also the Reply-To on every escalation they raise,
    which means a wrong address quietly sends an engineer's reply nowhere.

    `current_password` is required whenever the email changes. Not verification
    - the new address is trusted as typed, by decision - but a guard so that a
    borrowed laptop or a stolen session token cannot silently move the account
    to an attacker's address and lock the owner out of their own workspace.
    Changing a name needs no such proof; it cannot be used to take anything.
    """

    full_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    job_title = serializers.CharField(required=False, allow_blank=True, max_length=120)
    email = serializers.EmailField(required=False)
    current_password = serializers.CharField(required=False, write_only=True)

    def validate_email(self, value: str) -> str:
        # Normalised the same way the manager does on create, or `Rizwan@x.com`
        # would pass the uniqueness check against a stored `rizwan@x.com` and
        # fail at the database instead.
        value = value.strip().lower()
        user = self.context["user"]

        if value != user.email:
            from django.contrib.auth import get_user_model

            if get_user_model().objects.filter(email=value).exclude(pk=user.pk).exists():
                raise serializers.ValidationError("That address is already in use.")
        return value

    def validate(self, attrs):
        user = self.context["user"]
        changing_email = "email" in attrs and attrs["email"] != user.email

        if changing_email and not user.check_password(attrs.get("current_password") or ""):
            raise serializers.ValidationError(
                {"current_password": "Enter your current password to change your email address."}
            )
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    """Changing your own password.

    The current password is checked even though the request is authenticated: a
    session that has been left open is not proof of identity, and a password
    change is the one action that locks the real owner out.
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        if not self.context["user"].check_password(value):
            raise serializers.ValidationError("That is not your current password.")
        return value

    def validate_new_password(self, value: str) -> str:
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(value, self.context["user"])
        except DjangoValidationError as exc:
            # Django returns a list; DRF renders one string per entry, which is
            # what the form needs to show all the rules that were broken.
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=12)
    new_password = serializers.CharField(write_only=True)
