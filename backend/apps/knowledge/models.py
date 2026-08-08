"""Knowledge base: runbooks, their extracted assets, and the retrievable chunks.

The shape of these three models encodes the pipeline's central design choice
(D-054): a Gemini image description is not stored as a separate searchable
object. It is spliced back into the document's linear text stream at the image's
original position before chunking, so a diagram is retrieved together with the
procedure that references it rather than as an orphaned blob.

DocumentAsset therefore exists for provenance and re-indexing, not for search.
Search only ever touches DocumentChunk.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField

from apps.tenancy.managers import TenantScopedModel


class DocumentStatus(models.TextChoices):
    """Real ingestion states (D-083).

    These replaced the prototype's Popular / Updated / Policy badges, which
    tracked nothing. A user seeing INDEXING knows their upload is not yet
    answerable; a user seeing a "Popular" badge knew nothing at all.
    """

    UPLOADED = "UPLOADED", "Uploaded"
    PARSING = "PARSING", "Parsing"
    DESCRIBING = "DESCRIBING", "Describing images"
    EMBEDDING = "EMBEDDING", "Embedding"
    INDEXED = "INDEXED", "Indexed"
    FAILED = "FAILED", "Failed"


class FileType(models.TextChoices):
    PDF = "PDF", "PDF"
    DOCX = "DOCX", "Word"
    MD = "MD", "Markdown"


class Category(TenantScopedModel):
    """Per-tenant runbook grouping. Counts are derived, never stored."""

    name = models.CharField(max_length=80)
    abbreviation = models.CharField(max_length=4, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_category_per_tenant")
        ]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Document(TenantScopedModel):
    """An uploaded runbook."""

    title = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )

    storage_key = models.CharField(max_length=512, help_text="Object storage key, never a URL.")
    file_type = models.CharField(max_length=8, choices=FileType.choices)
    size_bytes = models.PositiveBigIntegerField(default=0)
    # Deduplicates re-uploads of an identical file and lets a re-index verify
    # the bytes have not changed underneath it.
    checksum = models.CharField(max_length=64, db_index=True, blank=True)

    status = models.CharField(
        max_length=12,
        choices=DocumentStatus.choices,
        default=DocumentStatus.UPLOADED,
        db_index=True,
    )
    error = models.TextField(blank=True)

    page_count = models.PositiveIntegerField(default=0)
    image_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    indexed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self) -> str:
        return self.title

    @property
    def is_answerable(self) -> bool:
        """Only an indexed document can be retrieved from."""
        return self.status == DocumentStatus.INDEXED


class DocumentAsset(models.Model):
    """An image extracted from a document, and the text Gemini produced for it.

    Not tenant-scoped directly: it is reachable only through its Document, which
    is. Kept for provenance - so a re-index can reuse a description instead of
    paying Gemini twice - and for showing an operator why a chunk says what it
    says.
    """

    class DescribeStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        DESCRIBED = "DESCRIBED", "Described"
        SKIPPED = "SKIPPED", "Skipped"
        FAILED = "FAILED", "Failed"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="assets")

    # Position in the document's linear block stream. This is what makes D-054
    # possible: the description is spliced back exactly here.
    block_index = models.PositiveIntegerField()
    page = models.PositiveIntegerField(default=0)

    mime_type = models.CharField(max_length=40)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    # Perceptual dedupe within a document: a logo repeated on 200 pages is one
    # Gemini call, not 200 (D-058).
    sha256 = models.CharField(max_length=64, db_index=True)

    description_text = models.TextField(blank=True)
    describe_status = models.CharField(
        max_length=10, choices=DescribeStatus.choices, default=DescribeStatus.PENDING
    )
    describe_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("document", "block_index")
        constraints = [
            models.UniqueConstraint(fields=["document", "block_index"], name="uniq_asset_per_block")
        ]

    def __str__(self) -> str:
        return f"{self.document_id}#{self.block_index}"


class DocumentChunk(TenantScopedModel):
    """A retrievable passage. The only thing search ever touches.

    A chunk derived from an image description carries from_image=True, so an
    answer can say where its evidence came from - and so a bad Gemini
    description can be traced rather than guessed at.
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    ordinal = models.PositiveIntegerField()
    text = models.TextField()

    # Dimension comes from settings at migration time (D-060). Changing
    # EMBEDDING_DIM without a re-embed corrupts retrieval silently, which is why
    # the health check and a test both assert the configured value.
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM, null=True, blank=True)

    from_image = models.BooleanField(default=False)
    source_page = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("document", "ordinal")
        constraints = [
            models.UniqueConstraint(fields=["document", "ordinal"], name="uniq_chunk_ordinal")
        ]
        indexes = [
            models.Index(fields=["tenant", "document"]),
            # Cosine distance, with the exact D-057 parameters. Built here rather
            # than in raw SQL so makemigrations --check stays honest about it.
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=settings.HNSW_M,
                ef_construction=settings.HNSW_EF_CONSTRUCTION,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_id}[{self.ordinal}]"
