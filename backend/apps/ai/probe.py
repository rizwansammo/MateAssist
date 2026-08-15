"""One real call against a stored key, to prove it works (D-155).

A saved key proves nothing. The credential can be valid while the model id is
retired, the base URL can point somewhere that answers 404, the account can lack
access to the model it names. Every one of those saves cleanly and then fails at
the only moment that matters - a user waiting on an answer.

Google withdrawing `gemini-1.5-flash` is the case that forced this: the key was
fine, the configuration was fine when it was written, and the first sign of
trouble was a failed screenshot in production.

So this makes the smallest possible real request through the same factory the
chat path uses. Not a model list - a list can include a model the account cannot
actually call. Only a completed call proves the whole chain.
"""

from __future__ import annotations

import logging

from .engines.factory import build_engine
from .models import Engine

logger = logging.getLogger(__name__)

# Costs a handful of tokens and takes about a second. Cheap enough that an
# operator can press the button as often as they like.
_TEXT_PROMPT = "Reply with the single word: OK"


def probe_png(size: int = 96) -> bytes:
    """A real image with visible structure.

    Not a 1x1 pixel: the Gemini 3.x models reject a degenerate image with
    "Unable to process input image", which reads exactly like a broken model id
    and would send an operator chasing the wrong problem.
    """
    import struct
    import zlib

    rows = []
    for y in range(size):
        row = bytearray([0])  # PNG filter byte
        for x in range(size):
            on_cross = abs(x - size // 2) < 6 or abs(y - size // 2) < 6
            value = 0 if on_cross else 255
            row += bytes([value, value, value])
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
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def check_key(key) -> dict:
    """Make one minimal live call. Never raises.

    Returns {ok, detail, model}. The provider's own error text is passed through
    verbatim, which is the opposite of the rule for chat (D-135) and correct
    here: the reader is the platform owner debugging their own configuration,
    and "model not found for API version v1beta" IS the answer. It never reaches
    a tenant user.
    """
    model = key.resolved_model

    try:
        engine = build_engine(key, key.reveal())

        if key.engine == Engine.VISION:
            engine.describe(probe_png(), mime_type="image/png", purpose="runbook")
        else:
            from .engines.base import TextMessage

            engine.complete([TextMessage(role="user", content=_TEXT_PROMPT)], max_tokens=16)

    except Exception as exc:  # noqa: BLE001 - every failure is a report, not a crash
        logger.info("key check failed for %s: %s", key, exc)
        return {"ok": False, "model": model, "detail": _readable(exc)}

    return {"ok": True, "model": model, "detail": f"{model} responded."}


def _readable(exc: Exception) -> str:
    """Trim the provider's message to the part an operator can act on.

    Google's 404 body is three sentences of which the first is the whole story,
    and burying it behind a scrollbar helps nobody.
    """
    text = str(exc).strip()
    marker = "'message': '"
    if marker in text:
        start = text.index(marker) + len(marker)
        end = text.find("'", start)
        if end > start:
            text = text[start:end]
    return text[:300] or exc.__class__.__name__
