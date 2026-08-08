"""Object storage for uploaded runbooks (D-013).

Keys are namespaced by tenant. That is organisational, not a security boundary -
authorisation happens in Django before any key is constructed, and the bucket is
private with no anonymous access (verified by the Phase 0 gate).
"""

from __future__ import annotations

import hashlib
import uuid
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def build_key(tenant_id: int, filename: str) -> str:
    """A random key, not the user's filename.

    The original name is kept in Document.title. Deriving the storage key from
    it would let a filename decide a path.
    """
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"tenants/{tenant_id}/documents/{uuid.uuid4().hex}.{suffix}"


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(key: str, data: bytes, content_type: str) -> None:
    _client().put_object(
        Bucket=settings.S3_BUCKET_NAME, Key=key, Body=data, ContentType=content_type
    )


def get(key: str) -> bytes:
    response = _client().get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
    return response["Body"].read()


def delete(key: str) -> None:
    _client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
