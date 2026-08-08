"""Splice image descriptions back into place, then chunk (D-054, D-055).

THE CENTRAL DESIGN CHOICE
    A Gemini description is not stored as its own searchable object. It is
    substituted for the image *at the image's own index in the block stream*,
    and only then is the document chunked.

    The consequence: a diagram's description lands in the same chunk as the
    procedure that referenced it. Retrieve that chunk and you get the step and
    the picture of the step together.

    The alternative - indexing descriptions separately - produces orphans. A
    chunk reading "the dialog shows Advanced Settings with SSL enabled" retrieves
    on its own with nothing to say which product, which procedure, or which step
    it belongs to. It looks like it works right up until someone asks a question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.conf import settings

from .parsers.base import ImageBlock, ParsedDocument, TextBlock

# ~4 characters per token is close enough for chunk sizing and avoids dragging a
# tokeniser into the hot path. Only the embedder's real limit matters, and it
# truncates safely.
CHARS_PER_TOKEN = 4

IMAGE_TEMPLATE = "[Figure{page}: {description}]"


@dataclass
class Chunk:
    text: str
    ordinal: int
    from_image: bool = False
    source_page: int = 0
    heading_path: list[str] = field(default_factory=list)

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.text) // CHARS_PER_TOKEN)


def splice(parsed: ParsedDocument, descriptions: dict[int, str]) -> list[TextBlock]:
    """Replace each ImageBlock with its description, in place.

    `descriptions` is keyed by block index - the same index persisted on
    DocumentAsset.block_index - so a description can only ever land where its
    image was.

    An image with no usable description is dropped rather than replaced with a
    placeholder: "[image]" is noise that dilutes the embedding of the chunk it
    lands in, making the surrounding text harder to retrieve, not easier.
    """
    result: list[TextBlock] = []

    for index, block in enumerate(parsed.blocks):
        if isinstance(block, TextBlock):
            result.append(block)
            continue

        if not isinstance(block, ImageBlock):
            continue

        description = (descriptions.get(index) or "").strip()
        if not description:
            continue

        page_note = f" (page {block.page})" if block.page else ""
        result.append(
            TextBlock(
                text=IMAGE_TEMPLATE.format(page=page_note, description=description),
                page=block.page,
                heading_path=list(block.heading_path),
            )
        )

    return result


def chunk_blocks(blocks: list[TextBlock]) -> list[Chunk]:
    """Heading-aware chunking at ~512 tokens with 15% overlap (D-055).

    Overlap exists so a procedure split across a boundary is still retrievable
    from either side; without it, the answer to "what comes after step 4" can
    live in a chunk that the question does not match.
    """
    target_chars = settings.CHUNK_TARGET_TOKENS * CHARS_PER_TOKEN
    overlap_chars = int(target_chars * settings.CHUNK_OVERLAP_RATIO)

    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    current_heading: list[str] = []
    current_page = 0
    contains_image = False

    def emit():
        nonlocal current, current_len, contains_image
        body = "\n\n".join(current).strip()
        if body:
            prefix = " > ".join(current_heading)
            chunks.append(
                Chunk(
                    # The heading breadcrumb is embedded with the text: a chunk
                    # saying "restart the spooler" is far more retrievable when
                    # it carries "Printers > HP LaserJet M479" with it.
                    text=f"{prefix}\n\n{body}" if prefix else body,
                    ordinal=len(chunks),
                    from_image=contains_image,
                    source_page=current_page,
                    heading_path=list(current_heading),
                )
            )
        current = []
        current_len = 0
        contains_image = False

    for block in blocks:
        piece = block.text.strip()
        if not piece:
            continue

        is_image_text = piece.startswith("[Figure")

        # A heading change is a natural seam - prefer it over a size-based split.
        if block.heading_path != current_heading and current:
            emit()
        current_heading = list(block.heading_path)
        if not current:
            current_page = block.page

        for segment in _split_oversized(piece, target_chars):
            if current_len + len(segment) > target_chars and current:
                tail = _overlap_tail(current, overlap_chars)
                emit()
                current_heading = list(block.heading_path)
                current_page = block.page
                if tail:
                    current.append(tail)
                    current_len += len(tail)

            current.append(segment)
            current_len += len(segment)
            contains_image = contains_image or is_image_text

    emit()
    return chunks


def _split_oversized(text: str, target_chars: int) -> list[str]:
    """Break a block that alone exceeds the target, on sentence boundaries."""
    if len(text) <= target_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts: list[str] = []
    buffer = ""

    for sentence in sentences:
        if len(buffer) + len(sentence) + 1 > target_chars and buffer:
            parts.append(buffer.strip())
            buffer = ""
        buffer += sentence + " "
        # A single sentence longer than the target (a table row, a long command)
        # gets hard-cut rather than dropped.
        while len(buffer) > target_chars:
            parts.append(buffer[:target_chars])
            buffer = buffer[target_chars:]

    if buffer.strip():
        parts.append(buffer.strip())
    return parts


def _overlap_tail(pieces: list[str], overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return ""
    joined = "\n\n".join(pieces)
    return joined[-overlap_chars:].strip() if len(joined) > overlap_chars else ""
