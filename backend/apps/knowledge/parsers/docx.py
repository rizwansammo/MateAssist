"""DOCX parsing (D-052).

python-docx exposes paragraphs and the document part separately, so walking
`paragraphs` alone would collect text and lose every image's position. Instead
this walks the underlying XML body in order and resolves each inline image
reference against the package parts as it goes - which is what preserves the
interleaving D-054 depends on.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from .base import ImageBlock, ParsedDocument, ParseError, TextBlock

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

HEADING_PREFIX = "Heading"
MIN_IMAGE_BYTES = 2_048  # icons and bullet glyphs are not worth a vision call


def parse_docx(path: str | Path) -> ParsedDocument:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ParseError("python-docx is not installed.") from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Could not open the Word document: {exc}") from exc

    max_images = getattr(settings, "VISION_MAX_IMAGES_PER_DOCUMENT", 400)
    part = document.part

    blocks: list = []
    heading_path: list[str] = []
    images_emitted = 0

    for element in document.element.body.iter():
        if element.tag != f"{W_NS}p":
            continue

        paragraph_text = "".join(node.text or "" for node in element.iter(f"{W_NS}t")).strip()
        style = _paragraph_style(element)

        if style and style.startswith(HEADING_PREFIX) and paragraph_text:
            level = _heading_level(style)
            # Truncate the breadcrumb to this level, then append - so H2 after
            # H2 replaces rather than nests.
            heading_path = heading_path[: level - 1] + [paragraph_text]

        if paragraph_text:
            blocks.append(TextBlock(text=paragraph_text, heading_path=list(heading_path)))

        # Images declared inside this paragraph, in document order.
        for blip in element.iter(f"{A_NS}blip"):
            if images_emitted >= max_images:
                break
            embed_id = blip.get(f"{R_NS}embed")
            if not embed_id:
                continue
            try:
                image_part = part.related_parts[embed_id]
                data = image_part.blob
            except Exception:  # noqa: BLE001, S112
                continue  # a missing relationship must not fail the document

            if len(data) < MIN_IMAGE_BYTES:
                continue

            blocks.append(
                ImageBlock(
                    data=data,
                    mime_type=_mime_for(image_part.partname),
                    heading_path=list(heading_path),
                )
            )
            images_emitted += 1

    return ParsedDocument(blocks=blocks, page_count=0)


def _paragraph_style(element) -> str:
    style_element = element.find(f"{W_NS}pPr/{W_NS}pStyle")
    if style_element is None:
        return ""
    return style_element.get(f"{W_NS}val", "") or ""


def _heading_level(style: str) -> int:
    tail = style[len(HEADING_PREFIX) :].strip()
    return int(tail) if tail.isdigit() else 1


def _mime_for(partname) -> str:
    extension = str(partname).rsplit(".", 1)[-1].lower()
    if extension in {"jpg", "jpeg"}:
        return "image/jpeg"
    if extension in {"png", "gif", "webp"}:
        return f"image/{extension}"
    return "image/png"
