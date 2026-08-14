"""Knowledge base API.

Upload is restricted to TENANT_ADMIN (D-090); every tenant member can read.
"""

from __future__ import annotations

import logging

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.audit.models import record
from apps.tenancy.models import Membership, Role

from . import storage
from .models import Category, Document, DocumentStatus, FileType
from .serializers import (
    CategorySerializer,
    DocumentAssetSerializer,
    DocumentChunkSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
)
from .tasks import ingest_document

logger = logging.getLogger(__name__)

EXTENSION_TO_TYPE = {"pdf": FileType.PDF, "docx": FileType.DOCX, "md": FileType.MD}
# Sniffed from the leading bytes, not trusted from the extension (D-131).
MAGIC = {
    FileType.PDF: (b"%PDF",),
    FileType.DOCX: (b"PK\x03\x04",),  # DOCX is a zip container
}


class IsTenantAdmin(BasePermission):
    """Workspace administrators only - reads included (D-140).

    This used to exempt GET, on the reasoning that runbooks are for everyone.
    That was wrong, and not only for the browsable list: it made
    `/knowledge/documents/{id}/chunks/` readable by any authenticated member, so
    every end user could pull the full text of every runbook through the API
    whether or not a menu item existed.

    IT runbooks are written for IT. They routinely carry admin console paths,
    service account names, network topology, and "verify identity by calling the
    number on record" instructions that stop working once the person being
    verified has read them.

    The assistant still retrieves from all of it - that is the product. What is
    removed is *browsing*: the answer reaches the user through the assistant,
    which is the point of the assistant.
    """

    message = "Only a workspace administrator can access runbooks directly."

    def has_permission(self, request, view) -> bool:
        tenant = getattr(request, "tenant", None)
        if tenant is None or not request.user or not request.user.is_authenticated:
            return False
        return Membership.all_objects.filter(
            user=request.user, tenant=tenant, role=Role.TENANT_ADMIN
        ).exists()


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get_queryset(self):
        return Category.objects.annotate(document_count=Count("documents"))

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, IsTenantAdmin]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        # RLS already scopes this; the manager filter is defence in depth (D-022).
        queryset = Document.objects.select_related("category", "uploaded_by")
        status_filter = self.request.query_params.get("status")
        if status_filter in DocumentStatus.values:
            queryset = queryset.filter(status=status_filter)
        return queryset

    @extend_schema(request=DocumentUploadSerializer, responses={202: DocumentSerializer})
    def create(self, request, *args, **kwargs):
        payload = DocumentUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        upload = payload.validated_data["file"]

        from django.conf import settings

        if upload.size > settings.UPLOAD_MAX_BYTES:
            return Response(
                {"detail": f"File exceeds the {settings.UPLOAD_MAX_BYTES // 1048576} MB limit."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        extension = (upload.name.rsplit(".", 1)[-1] if "." in upload.name else "").lower()
        file_type = EXTENSION_TO_TYPE.get(extension)
        if file_type is None:
            return Response(
                {"detail": "Only .pdf, .docx and .md files are accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = upload.read()

        # Content sniff. An attacker renaming a payload to .pdf gets rejected
        # here rather than handed to a parser that trusts the extension.
        expected = MAGIC.get(file_type)
        if expected and not any(data.startswith(prefix) for prefix in expected):
            return Response(
                {"detail": f"File content does not match a {file_type} document."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant = request.tenant
        checksum = storage.checksum(data)

        existing = Document.objects.filter(checksum=checksum).first()
        if existing:
            return Response(
                {
                    "detail": f"This file is already uploaded as '{existing.title}'.",
                    "document": DocumentSerializer(existing).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        key = storage.build_key(tenant.id, upload.name)
        storage.put(key, data, upload.content_type or "application/octet-stream")

        document = Document.objects.create(
            tenant=tenant,
            title=(payload.validated_data.get("title") or upload.name).strip()[:255],
            category=payload.validated_data.get("category"),
            storage_key=key,
            file_type=file_type,
            size_bytes=len(data),
            checksum=checksum,
            uploaded_by=request.user,
            status=DocumentStatus.UPLOADED,
        )

        record(
            "rag.upload",
            tenant=tenant,
            actor=request.user,
            target=document.title,
            document_id=document.id,
            file_type=file_type,
            size_bytes=len(data),
        )

        # Queued, not run inline: parsing plus a Gemini call per image can take
        # minutes, and an HTTP request is the wrong place to spend them.
        ingest_document.delay(tenant.id, document.id)

        return Response(DocumentSerializer(document).data, status=status.HTTP_202_ACCEPTED)

    def perform_destroy(self, instance):
        key, title = instance.storage_key, instance.title
        tenant = instance.tenant
        instance.delete()
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001
            # An orphaned object is a cleanup job; a 500 on delete is a user
            # staring at a document that says it is gone and is not.
            logger.exception("could not remove %s from storage", key)
        record("rag.delete", tenant=tenant, target=title)

    @extend_schema(responses={202: DocumentSerializer})
    @action(detail=True, methods=["post"])
    def reindex(self, request, pk=None):
        document = self.get_object()
        document.status = DocumentStatus.UPLOADED
        document.error = ""
        document.save(update_fields=["status", "error", "updated_at"])
        ingest_document.delay(document.tenant_id, document.id)
        record("rag.reindex", tenant=document.tenant, actor=request.user, target=document.title)
        return Response(DocumentSerializer(document).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={200: DocumentChunkSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def chunks(self, request, pk=None):
        document = self.get_object()
        return Response(DocumentChunkSerializer(document.chunks.all()[:200], many=True).data)

    @extend_schema(responses={200: DocumentAssetSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def assets(self, request, pk=None):
        """Which figures were found, and what Gemini said about each."""
        document = self.get_object()
        return Response(DocumentAssetSerializer(document.assets.all(), many=True).data)
