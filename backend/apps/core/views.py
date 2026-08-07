"""Core API views."""

from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import health


class HealthView(APIView):
    """Liveness and dependency health.

    Public and unauthenticated by explicit opt-out: DRF denies by default
    (see REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES), and a health endpoint that
    needs a token is useless to a load balancer.

    Returns 503 when a required dependency is down so orchestrators can act on
    the status code without parsing the body.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="health",
        summary="Dependency health",
        description=(
            "Exercises PostgreSQL, pgvector, Redis and the Celery broker for real. "
            "200 when healthy or degraded, 503 when a required dependency is down."
        ),
        responses={200: dict, 503: dict},
        examples=[
            OpenApiExample(
                "healthy",
                value={
                    "status": "ok",
                    "version": "0.1.0",
                    "checks": [
                        {
                            "name": "database",
                            "status": "ok",
                            "detail": "PostgreSQL 17.10",
                            "latency_ms": 2.14,
                            "required": True,
                        }
                    ],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request: Request) -> Response:
        overall, checks = health.run_all()

        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if overall == health.ERROR
            else status.HTTP_200_OK
        )

        return Response(
            {
                "status": overall,
                "version": settings.SPECTACULAR_SETTINGS["VERSION"],
                "debug": settings.DEBUG,
                "checks": [c.as_dict() for c in checks],
            },
            status=http_status,
        )
