"""Workspace settings, owned by the tenant's own administrator (D-151)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import Level, record

from .context import platform_scope
from .models import ASSISTANT_INSTRUCTIONS_MAX, Membership, Role


class IsWorkspaceAdmin(BasePermission):
    """Administrators of THIS workspace, for reads as well as writes.

    Reads are restricted too: the instructions can name internal tooling and
    local policy, and an end user has no reason to read the configuration of the
    assistant they are talking to.
    """

    message = "Only a workspace administrator can change these settings."

    def has_permission(self, request, view) -> bool:
        tenant = getattr(request, "tenant", None)
        if tenant is None or not request.user or not request.user.is_authenticated:
            return False
        return Membership.all_objects.filter(
            user=request.user, tenant=tenant, role=Role.TENANT_ADMIN
        ).exists()


class WorkspaceSettingsSerializer(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    support_email = serializers.EmailField(required=False, allow_blank=True)
    assistant_instructions = serializers.CharField(
        required=False, allow_blank=True, max_length=ASSISTANT_INSTRUCTIONS_MAX
    )
    assistant_instructions_limit = serializers.IntegerField(read_only=True)

    # ---- outbound mail (D-154) ----
    #
    # Note what is absent: there is no field that READS the password. The API
    # can only report whether one is set, because a serializer field that
    # returned it would put a working mail credential into every browser session
    # and every log of a response body. Same rule as the provider vault (D-072):
    # write-only is the absence of a read path, not a flag.
    smtp_host = serializers.CharField(required=False, allow_blank=True, max_length=255)
    smtp_port = serializers.IntegerField(required=False, min_value=1, max_value=65535)
    smtp_username = serializers.CharField(required=False, allow_blank=True, max_length=255)
    smtp_password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    smtp_use_tls = serializers.BooleanField(required=False)
    smtp_from_email = serializers.EmailField(required=False, allow_blank=True)
    smtp_password_set = serializers.BooleanField(read_only=True)
    smtp_configured = serializers.BooleanField(read_only=True)

    def validate_assistant_instructions(self, value: str) -> str:
        # Length is capped at the model too. Enforced here as well so the caller
        # gets a field error rather than a database exception, and because this
        # text rides in EVERY request - an unbounded block is a permanent tax on
        # every question the workspace asks.
        return value.strip()


class WorkspaceSettingsView(APIView):
    """Read and update the settings a workspace owns.

    Deliberately narrow. Plan, region and suspension are commercial state owned
    by the platform, not by the customer, so they are absent - a workspace must
    not be able to upgrade its own plan or unsuspend itself.
    """

    permission_classes = [IsAuthenticated, IsWorkspaceAdmin]

    @extend_schema(responses={200: WorkspaceSettingsSerializer})
    def get(self, request):
        return Response(self._payload(request.tenant))

    @extend_schema(
        request=WorkspaceSettingsSerializer, responses={200: WorkspaceSettingsSerializer}
    )
    def patch(self, request):
        payload = WorkspaceSettingsSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        tenant = request.tenant
        changed = []
        for field in (
            "support_email",
            "assistant_instructions",
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_use_tls",
            "smtp_from_email",
            "smtp_from_name",
        ):
            if field in data and getattr(tenant, field) != data[field]:
                setattr(tenant, field, data[field])
                changed.append(field)

        # The password is sealed, never assigned directly. An empty string means
        # "clear it"; omitting the field entirely means "leave it alone", so
        # saving the form without retyping the password does not wipe it - which
        # is what a write-only field does if you are careless.
        if "smtp_password" in data:
            tenant.set_smtp_password(data["smtp_password"])
            changed.append("smtp_password_ciphertext")

        if changed:
            tenant.save(update_fields=changed)
            # Audited: the instructions shape every answer the workspace gets,
            # so "why did the assistant start saying that?" needs an answer.
            # The text itself is not recorded - only that it changed and by how
            # much, since the audit log holds metadata, never payloads (D-114).
            record(
                "workspace.settings",
                tenant=tenant,
                actor=request.user,
                level=Level.INFO,
                target=tenant.name,
                fields=changed,
                instructions_length=len(tenant.assistant_instructions),
            )

        return Response(self._payload(tenant), status=status.HTTP_200_OK)

    @staticmethod
    def _payload(tenant) -> dict:
        return {
            "name": tenant.name,
            "slug": tenant.slug,
            "support_email": tenant.support_email,
            "assistant_instructions": tenant.assistant_instructions,
            "assistant_instructions_limit": ASSISTANT_INSTRUCTIONS_MAX,
            "smtp_host": tenant.smtp_host,
            "smtp_port": tenant.smtp_port,
            "smtp_username": tenant.smtp_username,
            "smtp_use_tls": tenant.smtp_use_tls,
            "smtp_from_email": tenant.smtp_from_email,
            # Whether a password exists, never the password.
            "smtp_password_set": bool(tenant.smtp_password_ciphertext),
            "smtp_configured": tenant.has_smtp,
        }


class WorkspaceMailTestView(APIView):
    """Send a real test message so an administrator can prove the settings work.

    Without it, the first exercise of a workspace's mail configuration is a real
    user's failed escalation - noticed only when nobody answers them.
    """

    permission_classes = [IsAuthenticated, IsWorkspaceAdmin]

    @extend_schema(responses={200: dict})
    def post(self, request):
        from . import mail

        tenant = request.tenant
        recipient = (request.data.get("to") or "").strip() or tenant.support_email
        if not recipient:
            return Response(
                {"sent": False, "detail": "Set an escalation address first, or pass one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = mail.send_test(tenant, recipient)
        record(
            "workspace.mail_test",
            tenant=tenant,
            actor=request.user,
            level=Level.INFO if result["sent"] else Level.WARN,
            target=recipient,
            sent=result["sent"],
            detail=result["detail"][:200],
        )
        return Response(result)


# ---------------------------------------------------------------- people ----


class WorkspaceUserSerializer(serializers.Serializer):
    """A member of this workspace, as their administrator sees them."""

    id = serializers.IntegerField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    job_title = serializers.CharField(source="user.job_title", read_only=True)
    display_name = serializers.CharField(source="user.display_name", read_only=True)
    initials = serializers.CharField(source="user.initials", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    last_seen_at = serializers.DateTimeField(source="user.last_seen_at", read_only=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    role = serializers.CharField(read_only=True)


class PasswordResetSerializer(serializers.Serializer):
    """Optionally set the password; otherwise one is generated.

    Generation is the better default and the reason the field is optional. An
    administrator resetting twelve accounts in a morning picks something they
    can retype, and that password is the one an attacker guesses first.
    """

    new_password = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_new_password(self, value: str) -> str:
        if not value:
            return ""
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


def _generate_password() -> str:
    """A password a human can read down a phone line without ambiguity.

    `secrets`, not `random`: this is a credential, and the default generator is
    seeded predictably enough to reconstruct. The alphabet omits characters that
    are misread when dictated or retyped - no O/0, no l/1/I - because the first
    thing a generated password has to survive is being communicated.
    """
    import secrets

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


class WorkspaceUserListView(APIView):
    """Everyone in this workspace (D-159).

    Reads memberships rather than users: a User is global and may belong to
    several workspaces, so listing users directly would be a way to enumerate
    people who are none of this administrator's business.
    """

    permission_classes = [IsWorkspaceAdmin]

    @extend_schema(responses={200: WorkspaceUserSerializer(many=True)})
    def get(self, request):
        memberships = (
            Membership.all_objects.filter(tenant=request.tenant)
            .select_related("user")
            .order_by("role", "user__email")
        )
        return Response(WorkspaceUserSerializer(memberships, many=True).data)


class WorkspaceUserPasswordResetView(APIView):
    """Reset a member's password.

    The target is resolved through a membership of THIS workspace, so a user id
    belonging to another tenant simply does not resolve. Authorisation is the
    lookup, not a check performed alongside it.
    """

    permission_classes = [IsWorkspaceAdmin]

    @extend_schema(request=PasswordResetSerializer, responses={200: None})
    def post(self, request, user_id: int):
        membership = get_object_or_404(
            Membership.all_objects.select_related("user"),
            tenant=request.tenant,
            user_id=user_id,
        )
        target = membership.user

        # A workspace administrator must never be able to reset the password of
        # someone who also holds platform ownership. It is the same User row, so
        # the new password would hand them the platform console - every tenant's
        # data and the credential vault - from an admin screen scoped to one
        # workspace. Platform owners carry a null tenant, so they never appear in
        # the list above; this closes the direct request.
        # Read outside the tenant scope. Asked from inside this workspace the
        # query returns nothing every time - RLS hides null-tenant rows - and
        # the guard would pass for exactly the account it exists to protect.
        with platform_scope():
            is_platform_owner = Membership.all_objects.filter(
                user=target, tenant__isnull=True, role=Role.PLATFORM_OWNER
            ).exists()

        if is_platform_owner:
            return Response(
                {"detail": "This account is managed by the platform owner."},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = PasswordResetSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        password = payload.validated_data.get("new_password") or _generate_password()
        target.set_password(password)
        target.save(update_fields=["password"])

        record(
            "workspace.password_reset",
            tenant=request.tenant,
            actor=request.user,
            level=Level.AUTH,
            target=target.email,
            generated=not payload.validated_data.get("new_password"),
        )

        # Returned once and never stored in readable form. The administrator has
        # to pass it on now; there is no screen that can show it again, which is
        # the same promise the credential vault makes.
        return Response({"password": password, "email": target.email})
