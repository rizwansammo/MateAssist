from rest_framework import serializers

from .models import Category, Document, DocumentAsset, DocumentChunk


class CategorySerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ("id", "name", "abbreviation", "document_count")


class DocumentSerializer(serializers.ModelSerializer):
    """Real ingestion metadata (D-082/D-083).

    Note what is absent and must stay absent: read time, view counts, and the
    Popular/Updated/Policy badges. Every field here is something the pipeline
    actually produces.
    """

    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.display_name", read_only=True, default=None
    )

    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "category",
            "category_name",
            "file_type",
            "size_bytes",
            "status",
            "error",
            "page_count",
            "image_count",
            "chunk_count",
            "uploaded_by_name",
            "created_at",
            "updated_at",
            "indexed_at",
        )
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False, allow_null=True
    )


class DocumentAssetSerializer(serializers.ModelSerializer):
    """Provenance: which figure produced which description, and where it sat."""

    class Meta:
        model = DocumentAsset
        fields = (
            "id",
            "block_index",
            "page",
            "mime_type",
            "width",
            "height",
            "describe_status",
            "description_text",
            "describe_error",
        )
        read_only_fields = fields


class DocumentChunkSerializer(serializers.ModelSerializer):
    """The embedding is deliberately not exposed - 384 floats per chunk is
    payload nobody reads, and it is derivable from the text anyway."""

    class Meta:
        model = DocumentChunk
        fields = ("id", "ordinal", "text", "from_image", "source_page", "token_count", "metadata")
        read_only_fields = fields
