"""Text & Reasoning Engine - DeepSeek (D-040).

THE ENGINE CONTRACT
    This client receives text and only text. Intent classification, RAG
    answering, ticket drafting and tool calling all happen here, on text chunks
    and on the *descriptions* Gemini produced for images (D-042).

    There is no parameter on this client capable of carrying an image, and
    _assert_text_only rejects anything image-shaped that reaches it by another
    route. Both are deliberate: the type signature stops the honest mistake, the
    runtime check stops the clever one.

    This is the single chokepoint every text call passes through, which is why
    the guard lives here rather than in each caller (D-043).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from django.conf import settings

from .base import (
    EngineError,
    EngineResult,
    ImagePayloadRejected,
    RateLimited,
    TextMessage,
)

# Substrings that betray an image payload smuggled into a string field.
_IMAGE_MARKERS = ("data:image/", "image_url", "inline_data", "b64_json")


def _assert_text_only(messages: Iterable[Any]) -> None:
    """Reject anything that is not a plain-text turn.

    Deliberately paranoid. The cost of a false positive is a loud developer
    error; the cost of a false negative is tenant image data reaching a provider
    that the architecture promises never sees it.
    """
    for index, message in enumerate(messages):
        if not isinstance(message, TextMessage):
            raise ImagePayloadRejected(
                f"messages[{index}] is {type(message).__name__}; TextEngine accepts "
                "only TextMessage. Images go to VisionEngine, and only its text "
                "output continues here (D-042)."
            )

        content = message.content
        if isinstance(content, (bytes, bytearray, memoryview)):
            raise ImagePayloadRejected(
                f"messages[{index}].content is binary. Bytes never reach the text engine."
            )
        if not isinstance(content, str):
            raise ImagePayloadRejected(
                f"messages[{index}].content is {type(content).__name__}, expected str. "
                "A parts list is how image payloads are usually smuggled in."
            )

        lowered = content.lower()
        for marker in _IMAGE_MARKERS:
            if marker in lowered:
                raise ImagePayloadRejected(
                    f"messages[{index}].content contains '{marker}', which looks like an "
                    "encoded image. Send Gemini's text description instead."
                )


class TextEngine:
    """DeepSeek client. Constructed per call with a key from the pool."""

    engine = "TEXT"

    def __init__(self, api_key: str, *, model: str | None = None, base_url: str | None = None):
        self.model = model or settings.DEEPSEEK_MODEL_CHAT
        self._base_url = base_url or settings.DEEPSEEK_API_BASE
        self._api_key = api_key
        self._cached_client = None

    def _client(self):
        # Imported lazily so the module can be imported (and the guard tested)
        # without the SDK or a network stack present. Cached on the instance for
        # the same reason as VisionEngine: a per-call client can have its
        # transport closed out from under an in-flight request, and it also
        # forces a new connection pool on every turn.
        if self._cached_client is None:
            from openai import OpenAI

            self._cached_client = OpenAI(
                api_key=self._api_key, base_url=self._base_url, timeout=60.0
            )
        return self._cached_client

    def complete(
        self,
        messages: list[TextMessage],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> EngineResult:
        _assert_text_only(messages)

        started = time.perf_counter()
        try:
            response = self._client().chat.completions.create(
                model=self.model,
                messages=[m.as_api_dict() for m in messages],
                tools=tools or None,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            if _looks_rate_limited(exc):
                raise RateLimited(str(exc)) from exc
            raise EngineError(f"DeepSeek call failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = response.choices[0]
        usage = getattr(response, "usage", None)

        tool_calls = []
        for call in getattr(choice.message, "tool_calls", None) or []:
            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                }
            )

        return EngineResult(
            text=choice.message.content or "",
            model=self.model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw_id=getattr(response, "id", "") or "",
        )

    def stream(self, messages: list[TextMessage], *, temperature: float = 0.2):
        """Yield content deltas for SSE (D-003). Phase 6 consumes this."""
        _assert_text_only(messages)
        try:
            stream = self._client().chat.completions.create(
                model=self.model,
                messages=[m.as_api_dict() for m in messages],
                temperature=temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:  # noqa: BLE001
            if _looks_rate_limited(exc):
                raise RateLimited(str(exc)) from exc
            raise EngineError(f"DeepSeek stream failed: {exc}") from exc


def _looks_rate_limited(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "429" in text or "quota" in text
