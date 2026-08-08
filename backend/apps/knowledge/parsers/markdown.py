"""Markdown parsing (D-053).

Headings become the breadcrumb path; fenced code blocks are kept intact so a
command sequence never gets split across chunks.

SECURITY: local image references are resolved and read; remote ones are logged
and skipped, never fetched. Following a URL out of a tenant-uploaded document
would turn ingestion into a server-side request forgery primitive pointed at
whatever the worker can reach - including cloud metadata endpoints.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .base import ImageBlock, ParsedDocument, TextBlock

logger = logging.getLogger(__name__)

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
FENCE = re.compile(r"^\s*```")

MIN_IMAGE_BYTES = 2_048
ALLOWED_SUFFIXES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def parse_markdown(path: str | Path) -> ParsedDocument:
    source = Path(path)
    text = source.read_text(encoding="utf-8", errors="replace")

    blocks: list = []
    heading_path: list[str] = []
    buffer: list[str] = []
    in_fence = False

    def flush():
        body = "\n".join(buffer).strip()
        buffer.clear()
        if body:
            blocks.append(TextBlock(text=body, heading_path=list(heading_path)))

    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        if in_fence:
            buffer.append(line)
            continue

        heading = HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            heading_path = heading_path[: level - 1] + [heading.group(2).strip()]
            blocks.append(TextBlock(text=heading.group(2).strip(), heading_path=list(heading_path)))
            continue

        image = IMAGE.search(line)
        if image:
            flush()
            block = _load_local_image(image.group(1), source.parent, heading_path)
            if block:
                blocks.append(block)
            continue

        buffer.append(line)

    flush()
    return ParsedDocument(blocks=blocks, page_count=0)


def _load_local_image(reference: str, base_dir: Path, heading_path: list[str]):
    if reference.startswith(("http://", "https://", "//", "data:")):
        logger.info("markdown: skipping remote image reference %s", reference[:120])
        return None

    candidate = (base_dir / reference).resolve()
    try:
        # Containment check: a reference like ../../etc/passwd must not escape
        # the upload directory even though it is a "local" path.
        candidate.relative_to(base_dir.resolve())
    except ValueError:
        logger.warning("markdown: rejected image path outside the document root: %s", reference)
        return None

    suffix = candidate.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES or not candidate.is_file():
        return None

    data = candidate.read_bytes()
    if len(data) < MIN_IMAGE_BYTES:
        return None

    return ImageBlock(
        data=data, mime_type=ALLOWED_SUFFIXES[suffix], heading_path=list(heading_path)
    )
