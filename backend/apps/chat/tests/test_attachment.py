"""A pasted screenshot must survive validation (D-153).

The gap this closes: every existing attachment test passed a *description*
string into prompt assembly, so nothing ever ran a real image through DRF's
ImageField. That field uses Pillow to verify the upload is genuinely an image
rather than a renamed payload - and Pillow was never a declared dependency.

The result was a 500 on the one path no test exercised, discovered by pasting a
terminal screenshot into the live product. So these tests build a real PNG and
push it through the actual serializer.
"""

import struct
import zlib

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.chat.serializers import SendMessageSerializer


def png_bytes(width: int = 48, height: int = 32) -> bytes:
    """A real PNG, built here rather than committed as a fixture.

    Pillow will actually decode this, which is the point - a hand-written byte
    string that merely starts with the PNG magic would pass a sniff test and
    fail the decode, proving nothing.
    """
    rows = []
    for y in range(height):
        row = bytearray([0])  # filter byte
        for x in range(width):
            row += bytes((30, 40, 60) if (x + y) % 8 else (16, 185, 129))
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def test_pillow_is_installed():
    """DRF's ImageField imports PIL lazily, inside to_python. An absent Pillow
    is therefore not an import error at startup - it is a 500 the first time a
    user attaches anything."""
    import PIL  # noqa: F401


def test_a_real_screenshot_passes_validation():
    upload = SimpleUploadedFile("terminal.png", png_bytes(), content_type="image/png")

    payload = SendMessageSerializer(data={"text": "what does this mean?", "image": upload})

    assert payload.is_valid(), payload.errors
    assert payload.validated_data["image"].name.endswith(".png")


def test_a_screenshot_with_no_text_gets_an_implied_question():
    """Pasting an error dialog and saying nothing is a complete question - the
    "what is this?" is implied, and refusing it would be pedantry."""
    upload = SimpleUploadedFile("error.png", png_bytes(), content_type="image/png")

    payload = SendMessageSerializer(data={"text": "", "image": upload})

    assert payload.is_valid(), payload.errors
    assert payload.validated_data["text"], "an empty question must be filled in, not rejected"


def test_a_renamed_file_is_refused():
    """The security half of ImageField. An executable renamed to .png must not
    reach the vision engine just because the extension says image."""
    upload = SimpleUploadedFile("payload.png", b"MZ\x90\x00 not an image", content_type="image/png")

    payload = SendMessageSerializer(data={"text": "look", "image": upload})

    assert not payload.is_valid()
    assert "image" in payload.errors


def test_an_empty_turn_is_still_refused():
    payload = SendMessageSerializer(data={"text": "", "image": None})
    assert not payload.is_valid()
