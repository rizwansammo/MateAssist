"""Vision & OCR Engine - Gemini (D-041).

THE ENGINE CONTRACT
    The only module in this codebase that accepts image bytes. It takes an
    image and returns text, and it is called for nothing else - no chat history,
    no retrieved chunks, no reasoning.

    Its output is the *only* thing that continues to DeepSeek. Bytes stop here
    (D-042).
"""

from __future__ import annotations

import time

from django.conf import settings

from .base import EngineError, EngineResult, RateLimited

ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/heic"}

# Ingestion and chat want different things from the same model: a runbook
# diagram needs procedural detail, an error screenshot needs the exact string.
PROMPTS = {
    "runbook": (
        "You are transcribing an image from an IT runbook for a retrieval system. "
        "Describe what it shows and transcribe ALL visible text verbatim: menu paths, "
        "field labels, button text, error codes, command lines, IP addresses and "
        "hostnames. If it is a diagram, describe the components and the flow between "
        "them. Write plain prose with no preamble. Do not speculate beyond the image."
    ),
    "screenshot": (
        "A user attached this screenshot to an IT support request. Transcribe every "
        "visible string exactly - dialog titles, error messages, error codes, "
        "application names and any highlighted field. Then state in one sentence what "
        "the screen appears to show. Plain prose, no preamble, no speculation."
    ),
}


class VisionEngine:
    """Gemini client. Images in, text out."""

    engine = "VISION"

    def __init__(self, api_key: str, *, model: str | None = None):
        self.model = model or settings.GEMINI_MODEL_VISION
        self._api_key = api_key

    def _client(self):
        from google import genai

        return genai.Client(api_key=self._api_key)

    def describe(
        self, image_bytes: bytes, *, mime_type: str, purpose: str = "runbook"
    ) -> EngineResult:
        if not isinstance(image_bytes, (bytes, bytearray)):
            raise EngineError("describe() expects raw image bytes.")
        if mime_type not in ALLOWED_MIME:
            raise EngineError(f"Unsupported image type {mime_type!r}.")

        from google.genai import types

        prompt = PROMPTS.get(purpose, PROMPTS["runbook"])
        started = time.perf_counter()

        try:
            response = self._client().models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=bytes(image_bytes), mime_type=mime_type),
                    prompt,
                ],
            )
        except Exception as exc:  # noqa: BLE001
            if _looks_rate_limited(exc):
                raise RateLimited(str(exc)) from exc
            raise EngineError(f"Gemini call failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage_metadata", None)

        return EngineResult(
            text=(response.text or "").strip(),
            model=self.model,
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            image_count=1,
            latency_ms=latency_ms,
        )


def _looks_rate_limited(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "429" in text or "quota" in text or "resource_exhausted" in text
