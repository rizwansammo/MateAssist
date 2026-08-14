"""Vision & OCR through an OpenAI-compatible endpoint (A-010).

Covers GPT-4o, Qwen-VL via OpenRouter, LLaVA via Ollama and anything else that
speaks the OpenAI chat protocol with `image_url` parts.

Same contract as the Gemini adapter (D-041): images in, text out, called for
nothing else. This module and vision_gemini are the only two places in the
codebase where image bytes exist.
"""

from __future__ import annotations

import base64
import time

from .base import EngineError, EngineResult, RateLimited
from .vision_gemini import ALLOWED_MIME, PROMPTS, _looks_rate_limited


class OpenAICompatibleVisionEngine:
    """Images in, text out - over the OpenAI protocol."""

    engine = "VISION"

    def __init__(self, api_key: str, *, model: str, base_url: str):
        if not model:
            raise EngineError("A vision model id is required for a generic endpoint.")
        if not base_url:
            raise EngineError("A base_url is required for a generic endpoint.")
        self.model = model
        self._base_url = base_url
        self._api_key = api_key
        self._cached_client = None

    def _client(self):
        # Cached for the reason recorded in A-009: a per-call client owns a
        # transport that can close before the request completes.
        if self._cached_client is None:
            from openai import OpenAI

            self._cached_client = OpenAI(
                api_key=self._api_key, base_url=self._base_url, timeout=90.0
            )
        return self._cached_client

    def describe(
        self, image_bytes: bytes, *, mime_type: str, purpose: str = "runbook"
    ) -> EngineResult:
        if not isinstance(image_bytes, (bytes, bytearray)):
            raise EngineError("describe() expects raw image bytes.")
        if mime_type not in ALLOWED_MIME:
            raise EngineError(f"Unsupported image type {mime_type!r}.")

        encoded = base64.b64encode(bytes(image_bytes)).decode("ascii")
        prompt = PROMPTS.get(purpose, PROMPTS["runbook"])
        started = time.perf_counter()

        try:
            response = self._client().chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                            },
                        ],
                    }
                ],
                # Generous on purpose: a reasoning model with a tight cap spends
                # the budget thinking and returns empty content with
                # finish_reason=length, which reads as a silent failure (A-010).
                max_tokens=1024,
            )
        except Exception as exc:  # noqa: BLE001
            if _looks_rate_limited(exc):
                raise RateLimited(str(exc)) from exc
            raise EngineError(f"Vision call failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)

        return EngineResult(
            text=(response.choices[0].message.content or "").strip(),
            model=self.model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            image_count=1,
            latency_ms=latency_ms,
        )
