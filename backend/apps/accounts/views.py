"""Authentication endpoints (D-030..D-036).

The refresh token is never returned in a response body. It is set as an
httpOnly, SameSite cookie scoped to /api/v1/auth, so JavaScript cannot read it
and it is not sent to any other endpoint. The access token goes in the body and
the SPA holds it in memory only.
"""

import contextlib

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenancy.models import Membership, Role

from .serializers import LoginSerializer, SessionSerializer, UserSerializer


def _set_refresh_cookie(response, refresh) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path=settings.REFRESH_COOKIE_PATH,
    )


def _session_payload(user, membership, tenant):
    refresh = RefreshToken.for_user(user)
    if tenant is not None:
        # Claims are a convenience for the client. They are NEVER the basis for
        # an access decision: the tenant is re-resolved from the Host header on
        # every request, so a forged claim buys nothing.
        refresh["tenant_id"] = tenant.id
    refresh["role"] = membership.role
    return refresh, {
        "access": str(refresh.access_token),
        "user": UserSerializer(user).data,
        "role": membership.role,
        "tenant": tenant,
    }


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: SessionSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        membership = serializer.validated_data["membership"]
        tenant = getattr(request, "tenant", None)

        refresh, payload = _session_payload(user, membership, tenant)
        response = Response(SessionSerializer(payload).data)
        _set_refresh_cookie(response, refresh)
        return response


class RefreshView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={200: SessionSerializer})
    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            return Response({"detail": "No session."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(raw)
            user_id = refresh["user_id"]
            # Rotation: the presented token is blacklisted immediately, so a
            # stolen refresh token is good for at most one use.
            refresh.blacklist()
        except TokenError:
            return Response({"detail": "Session expired."}, status=status.HTTP_401_UNAUTHORIZED)

        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            return Response({"detail": "Session expired."}, status=status.HTTP_401_UNAUTHORIZED)

        tenant = getattr(request, "tenant", None)
        # Membership is re-checked on every refresh, so revoking access takes
        # effect within the access-token lifetime rather than at next login.
        if tenant is None:
            membership = Membership.all_objects.filter(
                user=user, tenant__isnull=True, role=Role.PLATFORM_OWNER
            ).first()
        else:
            membership = Membership.all_objects.filter(user=user, tenant=tenant).first()
        if membership is None:
            return Response({"detail": "Access revoked."}, status=status.HTTP_401_UNAUTHORIZED)

        new_refresh, payload = _session_payload(user, membership, tenant)
        response = Response(SessionSerializer(payload).data)
        _set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            # Already expired or already blacklisted by rotation - either way the
            # user is signing out, so the cookie still gets cleared below.
            with contextlib.suppress(TokenError):
                RefreshToken(raw).blacklist()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SessionSerializer})
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            membership = Membership.all_objects.filter(
                user=request.user, tenant__isnull=True, role=Role.PLATFORM_OWNER
            ).first()
        else:
            membership = Membership.all_objects.filter(user=request.user, tenant=tenant).first()
        if membership is None:
            return Response({"detail": "Not a member of this workspace."}, status=403)

        return Response(
            {
                "user": UserSerializer(request.user).data,
                "role": membership.role,
                "tenant": (
                    None
                    if tenant is None
                    else {
                        "id": tenant.id,
                        "name": tenant.name,
                        "slug": tenant.slug,
                        "plan": tenant.plan,
                    }
                ),
            }
        )
