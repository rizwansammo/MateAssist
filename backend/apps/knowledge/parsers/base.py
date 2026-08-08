"""Document parsing into an ORDERED block stream.

Every parser returns the same thing: a flat list of blocks in the order they
appear in the document, with images occupying their real positions rather than
being collected into a separate bucket.

That ordering is the whole point (D-054). A block's index in this list becomes
DocumentAsset.block_index, which is how Gemini's description of an image gets
spliced back exactly where the image was before the text is chunked - so a
diagram ends up in the same chunk as the procedure that refers to it.

Collect the images separately and you lose that forever: the description becomes
an orphan that retrieves on its own, with no idea which step it illustrates.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    kind = "text"
    text: str
    page: int = 0
    # Breadcrumb of enclosing headings, so a chunk can carry "VPN Setup >
    # Troubleshooting" context that the raw text alone would not convey.
    heading_path: list[str] = field(default_factory=list)


@dataclass
class ImageBlock:
    kind = "image"
    data: bytes
    mime_type: str
    page: int = 0
    width: int = 0
    height: int = 0
    heading_path: list[str] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def pixels(self) -> int:
        return self.width * self.height


Block = TextBlock | ImageBlock


@dataclass
class ParsedDocument:
    blocks: list[Block]
    page_count: int = 0

    @property
    def text_blocks(self) -> list[TextBlock]:
        return [b for b in self.blocks if isinstance(b, TextBlock)]

    @property
    def image_blocks(self) -> list[tuple[int, ImageBlock]]:
        """(block_index, block) pairs - the index is what gets persisted."""
        return [(i, b) for i, b in enumerate(self.blocks) if isinstance(b, ImageBlock)]


class ParseError(Exception):
    """The document could not be read. Surfaced to the uploader verbatim."""
