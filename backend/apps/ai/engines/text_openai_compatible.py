"""Text & Reasoning Engine - any provider speaking the OpenAI chat protocol (D-040).

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
    """The text engine. Constructed per call with a key from the pool.

    Named for the PROTOCOL it speaks, not a vendor. A-010 made the provider a
    per-key setting, so the same class serves Groq, DeepSeek, OpenAI, Together
    or any other OpenAI-compatible endpoint - only `base_url` and `model`
    differ. The file was called text_deepseek.py long after that stopped being
    true, which invited exactly the question it deserved: "are we on DeepSeek?"
    """

    engine = "TEXT"

    def __init__(self, api_key: str, *, model: str | None = None, base_url: str | None = None):
        self.model = model or settings.TEXT_MODEL_DEFAULT
        self._base_url = base_url or settings.TEXT_API_BASE_DEFAULT
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
            # Named by ROLE, not vendor. This adapter serves Groq, DeepSeek, OpenAI,
            # Groq, Gemini's compatibility endpoint and anything else speaking
            # the protocol (A-010), so a hardcoded vendor name here is wrong for
            # most callers - it once reported a vendor name that was not serving the call.
            raise EngineError(f"Text engine call failed: {exc}") from exc

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

    def stream(
        self,
        messages: list[TextMessage],
        *,
        tools=None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ):
        """Yield content deltas for SSE (D-003).

        Usage lands on `self.last_usage` once the stream finishes. Without
        stream_options the provider reports no token counts at all, and the
        streaming path would silently go unmetered - breaking the "no provider
        call without a meter reading" invariant (D-110) for the single most
        frequent call in the product.

        TOOLS (D-161). `tools` was missing here entirely while `complete()` had
        it, so the chat box - which streams - never offered the model the
        escalation tool. The system prompt told it to use a tool it was never
        given, so it did the only thing left: described the tool to the user by
        name and offered to explain how to call it. Escalation was unreachable
        from the product's main surface for its whole life.

        Tool calls arrive as fragments spread across chunks: the name in one,
        the JSON arguments a few characters at a time in later ones. They are
        accumulated into `self.last_tool_calls` and are only complete once the
        stream ends - which is why the caller must read them after the loop,
        never during it.
        """
        _assert_text_only(messages)
        self.last_usage = EngineResult(model=self.model)
        self.last_tool_calls: list[dict] = []
        started = time.perf_counter()

        # Keyed by index, because a model may open more than one call and their
        # fragments interleave. Appending to a flat list would splice two sets
        # of arguments into one unparseable string.
        partial: dict[int, dict] = {}

        try:
            stream = self._client().chat.completions.create(
                model=self.model,
                messages=[m.as_api_dict() for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                tools=tools or None,
            )
            for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage:
                    self.last_usage.prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    self.last_usage.completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                # The usage-only final chunk carries no choices.
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if not delta:
                    continue

                for fragment in getattr(delta, "tool_calls", None) or []:
                    slot = partial.setdefault(
                        getattr(fragment, "index", 0), {"name": "", "arguments": ""}
                    )
                    function = getattr(fragment, "function", None)
                    if function is None:
                        continue
                    # The name usually arrives once, in full; the arguments
                    # arrive in pieces and must be concatenated in order.
                    if getattr(function, "name", None):
                        slot["name"] = function.name
                    if getattr(function, "arguments", None):
                        slot["arguments"] += function.arguments

                if delta.content:
                    yield delta.content
        except Exception as exc:  # noqa: BLE001
            if _looks_rate_limited(exc):
                raise RateLimited(str(exc)) from exc
            raise EngineError(f"Text stream failed: {exc}") from exc
        finally:
            self.last_usage.latency_ms = int((time.perf_counter() - started) * 1000)
            # Ordered by index so a multi-call response is reassembled the way
            # the model emitted it.
            self.last_tool_calls = [
                partial[index] for index in sorted(partial) if partial[index]["name"]
            ]


def _looks_rate_limited(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "429" in text or "quota" in text
