"""Shared engine types and errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class EngineError(Exception):
    """A provider call failed."""


class RateLimited(EngineError):
    """Provider returned 429 or a quota error. The pool cools this key down."""


class NoKeyAvailable(EngineError):
    """Every key for this engine is revoked, cooling down or over quota."""


class ImagePayloadRejected(TypeError):
    """An image reached the text engine.

    A TypeError rather than a plain exception on purpose: passing an image to
    the reasoning engine is a programming error, not a runtime condition to be
    caught and handled. It must fail loudly in development, never be retried.
    """


@dataclass(frozen=True)
class TextMessage:
    """A chat turn.

    `content` is typed str and nothing else. The absence of a parts list, an
    image field or an attachment field is the enforcement: there is no shape
    this dataclass can take that carries an image (D-043).
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    def as_api_dict(self) -> dict:
        payload: dict = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        return payload


@dataclass
class EngineResult:
    text: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    image_count: int = 0
    latency_ms: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    raw_id: str = ""
