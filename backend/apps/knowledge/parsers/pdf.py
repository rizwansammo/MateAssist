"""PDF parsing via PyMuPDF (D-051).

Text and images are emitted in reading order, interleaved, so an image lands
between the paragraphs that surrounded it rather than in a separate pile.

A page with no text layer is a scan. Rather than yielding nothing, the whole
page is rasterised and emitted as an image block, so Gemini OCRs it and the page
becomes searchable. Without that, scanned runbooks - which are common in IT
departments - would ingest as empty documents and silently answer nothing.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from .base import ImageBlock, ParsedDocument, ParseError, TextBlock

# Below this, an image is furniture: a bullet glyph, a rule, a spacer. Paying
# Gemini ~1,100 tokens to describe a 20x20 icon is the fastest way to burn an
# ingestion budget (D-058).
MIN_IMAGE_PIXELS = 10_000
# A page with less text than this is treated as a scan needing OCR.
SCAN_TEXT_THRESHOLD = 40


def parse_pdf(path: str | Path) -> ParsedDocument:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise ParseError("PyMuPDF is not installed.") from exc

    min_pixels = getattr(settings, "VISION_MIN_IMAGE_PIXELS", MIN_IMAGE_PIXELS)
    max_images = getattr(settings, "VISION_MAX_IMAGES_PER_DOCUMENT", 400)

    blocks = []
    images_emitted = 0

    try:
        document = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Could not open the PDF: {exc}") from exc

    try:
        for page_number, page in enumerate(document, start=1):
            text = (page.get_text("text") or "").strip()

            if len(text) < SCAN_TEXT_THRESHOLD:
                # Scanned page: rasterise at 2x so small print survives OCR.
                if images_emitted < max_images:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    blocks.append(
                        ImageBlock(
                            data=pixmap.tobytes("png"),
                            mime_type="image/png",
                            page=page_number,
                            width=pixmap.width,
                            height=pixmap.height,
                        )
                    )
                    images_emitted += 1
                if text:
                    blocks.append(TextBlock(text=text, page=page_number))
                continue

            blocks.append(TextBlock(text=text, page=page_number))

            for xref, *_ in page.get_images(full=True):
                if images_emitted >= max_images:
                    break
                try:
                    raw = document.extract_image(xref)
                except Exception:  # noqa: BLE001, S112
                    continue  # a broken embedded image must not fail the document

                width, height = raw.get("width", 0), raw.get("height", 0)
                if width * height < min_pixels:
                    continue

                extension = (raw.get("ext") or "png").lower()
                mime = "image/jpeg" if extension in {"jpg", "jpeg"} else f"image/{extension}"
                blocks.append(
                    ImageBlock(
                        data=raw["image"],
                        mime_type=mime,
                        page=page_number,
                        width=width,
                        height=height,
                    )
                )
                images_emitted += 1

        page_count = document.page_count
    finally:
        document.close()

    return ParsedDocument(blocks=blocks, page_count=page_count)
