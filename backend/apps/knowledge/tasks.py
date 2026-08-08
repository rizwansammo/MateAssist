"""Ingestion pipeline (Phase 5).

    store -> parse -> describe images (Gemini) -> splice -> chunk -> embed -> index

Runs as one task rather than a Celery chord. The fan-out shape suggests parallel
image calls, but the Gemini free tier rate-limits hard enough that concurrency
makes ingestion slower, not faster - every parallel call past the limit becomes a
429, a key cooldown, and a retry. Sequential with dedupe is the faster path here.

Tenant context is established first and everything runs inside it (D-023). A task
that cannot establish it fails closed rather than operating with RLS unset.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

from apps.ai import router
from apps.ai.engines import EngineError, NoKeyAvailable
from apps.audit.models import Level, record
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

from . import storage
from .chunking import chunk_blocks, splice
from .embeddings import get_embedding_provider
from .models import Document, DocumentAsset, DocumentChunk, DocumentStatus
from .parsers import ParseError, parse

logger = logging.getLogger(__name__)


def _arm_rls(tenant_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])


@shared_task(bind=True, name="knowledge.ingest_document", max_retries=2)
def ingest_document(self, tenant_id: int, document_id: int) -> dict:
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        raise ValueError(f"Unknown tenant {tenant_id}")

    with tenant_context(tenant_id), transaction.atomic():
        _arm_rls(tenant_id)
        document = Document.all_objects.filter(pk=document_id, tenant_id=tenant_id).first()
        if document is None:
            raise ValueError(f"Unknown document {document_id} for tenant {tenant_id}")

        try:
            return _run(document, tenant)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ingestion failed for document %s", document_id)
            document.status = DocumentStatus.FAILED
            document.error = str(exc)[:2000]
            document.save(update_fields=["status", "error", "updated_at"])
            record(
                "rag.index.failed",
                tenant=tenant,
                level=Level.ERROR,
                target=document.title,
                document_id=document.id,
                error=str(exc)[:300],
            )
            raise


def _run(document: Document, tenant: Tenant) -> dict:
    # -- parse ---------------------------------------------------------
    document.status = DocumentStatus.PARSING
    document.save(update_fields=["status", "updated_at"])

    payload = storage.get(document.storage_key)
    suffix = f".{document.file_type.lower()}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)

    try:
        parsed = parse(temp_path, file_type=document.file_type)
    except ParseError:
        raise
    finally:
        temp_path.unlink(missing_ok=True)

    image_blocks = parsed.image_blocks
    document.page_count = parsed.page_count
    document.image_count = len(image_blocks)
    document.status = DocumentStatus.DESCRIBING
    document.save(update_fields=["page_count", "image_count", "status", "updated_at"])

    # -- describe images (the ONLY Gemini call path) -------------------
    descriptions = _describe_images(document, tenant, image_blocks)

    # -- splice, chunk, embed ------------------------------------------
    document.status = DocumentStatus.EMBEDDING
    document.save(update_fields=["status", "updated_at"])

    spliced = splice(parsed, descriptions)
    chunks = chunk_blocks(spliced)

    if not chunks:
        raise ParseError(
            "No readable content was produced. The document may be empty, or a scan "
            "whose images could not be described."
        )

    provider = get_embedding_provider()
    vectors = provider.embed_passages([c.text for c in chunks])

    DocumentChunk.all_objects.filter(document=document).delete()  # idempotent re-index
    DocumentChunk.all_objects.bulk_create(
        [
            DocumentChunk(
                tenant=tenant,
                document=document,
                ordinal=chunk.ordinal,
                text=chunk.text,
                embedding=vector,
                from_image=chunk.from_image,
                source_page=chunk.source_page,
                token_count=chunk.token_estimate,
                metadata={"heading_path": chunk.heading_path},
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
    )

    document.chunk_count = len(chunks)
    document.status = DocumentStatus.INDEXED
    document.indexed_at = timezone.now()
    document.error = ""
    document.save(update_fields=["chunk_count", "status", "indexed_at", "error", "updated_at"])

    described = sum(1 for v in descriptions.values() if v)
    record(
        "rag.index",
        tenant=tenant,
        target=document.title,
        document_id=document.id,
        pages=document.page_count,
        images=document.image_count,
        described=described,
        chunks=len(chunks),
    )
    return {
        "document_id": document.id,
        "pages": document.page_count,
        "images": document.image_count,
        "described": described,
        "chunks": len(chunks),
    }


def _describe_images(document: Document, tenant: Tenant, image_blocks) -> dict[int, str]:
    """One Gemini call per DISTINCT image, keyed back to block index.

    Dedupe by content hash matters more than it looks: a company logo in a page
    header repeats on every page, and at ~1,100 tokens per image a 200-page
    runbook would spend 220k tokens describing the same logo 200 times (D-058).
    """
    DocumentAsset.objects.filter(document=document).delete()

    descriptions: dict[int, str] = {}
    by_hash: dict[str, str] = {}

    for block_index, block in image_blocks:
        digest = block.sha256
        asset = DocumentAsset(
            document=document,
            block_index=block_index,
            page=block.page,
            mime_type=block.mime_type,
            width=block.width,
            height=block.height,
            sha256=digest,
        )

        if digest in by_hash:
            asset.description_text = by_hash[digest]
            asset.describe_status = DocumentAsset.DescribeStatus.DESCRIBED
            asset.save()
            descriptions[block_index] = by_hash[digest]
            continue

        try:
            result = router.call_vision(
                block.data,
                mime_type=block.mime_type,
                purpose="runbook",
                tenant=tenant,
                user=document.uploaded_by,
            )
            text = (result.text or "").strip()
            asset.description_text = text
            asset.describe_status = (
                DocumentAsset.DescribeStatus.DESCRIBED
                if text
                else DocumentAsset.DescribeStatus.SKIPPED
            )
            if text:
                by_hash[digest] = text
                descriptions[block_index] = text
        except NoKeyAvailable as exc:
            # No usable Gemini key is a configuration problem, not a bad image.
            # Fail the whole document so it is not silently indexed half-blind.
            asset.describe_status = DocumentAsset.DescribeStatus.FAILED
            asset.describe_error = str(exc)[:500]
            asset.save()
            raise
        except EngineError as exc:
            # One unreadable image must not lose the whole runbook. Record it and
            # carry on; the document indexes with that figure missing, and the
            # asset row says why.
            logger.warning("image description failed (block %s): %s", block_index, exc)
            asset.describe_status = DocumentAsset.DescribeStatus.FAILED
            asset.describe_error = str(exc)[:500]

        asset.save()

    return descriptions
