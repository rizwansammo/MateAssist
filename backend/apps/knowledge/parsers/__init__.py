"""Document parsers.

Each returns an ordered block stream (see base.py) where images sit at their
real positions - the property the whole ingestion pipeline depends on (D-054).
"""

from pathlib import Path

from .base import Block, ImageBlock, ParsedDocument, ParseError, TextBlock

__all__ = [
    "Block",
    "ImageBlock",
    "ParsedDocument",
    "ParseError",
    "TextBlock",
    "parse",
]


def parse(path: str | Path, *, file_type: str) -> ParsedDocument:
    """Dispatch on the declared file type, never on the filename.

    The extension was already validated against a MIME sniff at upload (D-131);
    trusting it again here would undo that.
    """
    file_type = (file_type or "").upper()

    if file_type == "PDF":
        from .pdf import parse_pdf

        return parse_pdf(path)
    if file_type == "DOCX":
        from .docx import parse_docx

        return parse_docx(path)
    if file_type == "MD":
        from .markdown import parse_markdown

        return parse_markdown(path)

    raise ParseError(f"Unsupported file type {file_type!r}. Accepted: PDF, DOCX, MD.")
