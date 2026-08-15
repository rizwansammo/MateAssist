"""Workspace settings, owned by the tenant's own administrator (D-151)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import Level, record

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
