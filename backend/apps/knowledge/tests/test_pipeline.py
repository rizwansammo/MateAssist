"""Ingestion pipeline logic (D-054, D-055).

No network and no database: these test the transformation that makes the whole
phase worth building - an image description landing where the image was.
"""

import pytest
from django.test import override_settings

from apps.knowledge.chunking import chunk_blocks, splice
from apps.knowledge.parsers.base import ImageBlock, ParsedDocument, TextBlock

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def doc(*blocks) -> ParsedDocument:
    return ParsedDocument(blocks=list(blocks), page_count=1)


# ------------------------------------------------------------- splicing ----


def test_description_replaces_the_image_at_its_own_position():
    """The core claim of D-054."""
    parsed = doc(
        TextBlock(text="Step 2. Open the settings dialog."),
        ImageBlock(data=PNG, mime_type="image/png", page=1),
        TextBlock(text="Step 3. Apply the fix."),
    )

    blocks = splice(parsed, {1: "A dialog showing Advanced Settings with SSL enabled."})

    assert len(blocks) == 3
    assert blocks[0].text.startswith("Step 2")
    assert "Advanced Settings" in blocks[1].text
    assert blocks[2].text.startswith("Step 3")


def test_splicing_uses_block_index_not_image_order():
    """Descriptions are keyed by position in the block stream. If this ever
    keyed by 'nth image' instead, two images would silently swap descriptions."""
    parsed = doc(
        TextBlock(text="intro"),
        ImageBlock(data=PNG, mime_type="image/png"),
        TextBlock(text="middle"),
        ImageBlock(data=PNG + b"x", mime_type="image/png"),
    )

    blocks = splice(parsed, {1: "FIRST FIGURE", 3: "SECOND FIGURE"})

    assert "FIRST FIGURE" in blocks[1].text
    assert "SECOND FIGURE" in blocks[3].text


def test_undescribed_image_is_dropped_not_placeholdered():
    """A '[image]' placeholder is noise that dilutes the embedding of whatever
    chunk it lands in, making the surrounding text harder to retrieve."""
    parsed = doc(
        TextBlock(text="before"),
        ImageBlock(data=PNG, mime_type="image/png"),
        TextBlock(text="after"),
    )

    blocks = splice(parsed, {})  # Gemini failed on this one

    assert [b.text for b in blocks] == ["before", "after"]


def test_image_heading_context_is_preserved():
    parsed = doc(
        ImageBlock(data=PNG, mime_type="image/png", heading_path=["VPN", "Troubleshooting"])
    )
    blocks = splice(parsed, {0: "a network diagram"})
    assert blocks[0].heading_path == ["VPN", "Troubleshooting"]


# ------------------------------------------------------------- chunking ----


@override_settings(CHUNK_TARGET_TOKENS=512, CHUNK_OVERLAP_RATIO=0.15)
def test_figure_and_its_procedure_share_a_chunk():
    """The end the splicing exists to serve: retrieve the step, get the picture."""
    parsed = doc(
        TextBlock(text="Step 2. Open the GlobalProtect settings dialog."),
        ImageBlock(data=PNG, mime_type="image/png", page=1),
        TextBlock(text="Step 3. Add the UDP 3479 exclusion."),
    )
    blocks = splice(parsed, {1: "Advanced Settings panel listing excluded routes."})

    chunks = chunk_blocks(blocks)

    assert len(chunks) == 1
    assert "Step 2" in chunks[0].text
    assert "Advanced Settings" in chunks[0].text
    assert "Step 3" in chunks[0].text
    assert chunks[0].from_image is True


@override_settings(CHUNK_TARGET_TOKENS=512, CHUNK_OVERLAP_RATIO=0.15)
def test_from_image_is_false_for_pure_text():
    chunks = chunk_blocks([TextBlock(text="Just prose, no figures here.")])
    assert chunks[0].from_image is False


@override_settings(CHUNK_TARGET_TOKENS=32, CHUNK_OVERLAP_RATIO=0.15)
def test_long_document_splits_into_several_chunks():
    blocks = [TextBlock(text=f"Sentence number {i} of the runbook body.") for i in range(30)]
    chunks = chunk_blocks(blocks)
    assert len(chunks) > 1
    assert all(c.text.strip() for c in chunks)


@override_settings(CHUNK_TARGET_TOKENS=32, CHUNK_OVERLAP_RATIO=0.5)
def test_overlap_repeats_content_across_the_boundary():
    """Without overlap, the answer to "what comes after step 4" can sit in a
    chunk the question does not match."""
    blocks = [TextBlock(text=" ".join(f"word{i}" for i in range(200)))]
    chunks = chunk_blocks(blocks)
    assert len(chunks) > 1

    # Some token from the tail of chunk 0 must reappear at the head of chunk 1.
    tail = set(chunks[0].text.split()[-8:])
    head = set(chunks[1].text.split()[:20])
    assert tail & head, "no overlap between adjacent chunks"


@override_settings(CHUNK_TARGET_TOKENS=64, CHUNK_OVERLAP_RATIO=0.15)
def test_heading_breadcrumb_is_embedded_in_the_chunk_text():
    """A chunk saying "restart the spooler" is far more retrievable carrying
    "Printers > HP LaserJet M479" with it."""
    chunks = chunk_blocks(
        [TextBlock(text="Restart the print spooler.", heading_path=["Printers", "HP M479"])]
    )
    assert "Printers > HP M479" in chunks[0].text


@override_settings(CHUNK_TARGET_TOKENS=64, CHUNK_OVERLAP_RATIO=0.15)
def test_heading_change_starts_a_new_chunk():
    chunks = chunk_blocks(
        [
            TextBlock(text="VPN content here.", heading_path=["VPN"]),
            TextBlock(text="Printer content here.", heading_path=["Printers"]),
        ]
    )
    assert len(chunks) == 2


@override_settings(CHUNK_TARGET_TOKENS=16, CHUNK_OVERLAP_RATIO=0.0)
def test_a_single_oversized_block_is_split_rather_than_dropped():
    """A wide table row or a long command line must not vanish."""
    chunks = chunk_blocks([TextBlock(text="x" * 2000)])
    assert len(chunks) > 1
    assert sum(len(c.text) for c in chunks) >= 1900


def test_empty_document_yields_no_chunks():
    assert chunk_blocks([]) == []
    assert chunk_blocks([TextBlock(text="   ")]) == []


# ----------------------------------------------------------- parser guard ---


def test_markdown_refuses_remote_image_references():
    """Following a URL out of a tenant-uploaded document would make ingestion an
    SSRF primitive aimed at whatever the worker can reach."""
    from apps.knowledge.parsers.markdown import _load_local_image

    for reference in (
        "https://evil.example/x.png",
        "http://169.254.169.254/latest/meta-data/",
        "//evil.example/x.png",
        "data:image/png;base64,AAAA",
    ):
        assert _load_local_image(reference, __import__("pathlib").Path("."), []) is None


def test_markdown_refuses_paths_outside_the_document_root(tmp_path):
    from apps.knowledge.parsers.markdown import _load_local_image

    assert _load_local_image("../../../etc/passwd", tmp_path, []) is None


def test_unsupported_file_type_is_rejected():
    from apps.knowledge.parsers import ParseError, parse

    with pytest.raises(ParseError, match="Unsupported file type"):
        parse("whatever.exe", file_type="EXE")
