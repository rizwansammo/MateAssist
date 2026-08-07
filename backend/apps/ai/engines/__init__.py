"""Engine clients.

Two engines with fixed, non-overlapping roles (D-040/D-041). The handoff is
always image -> text -> reasoning, never image -> reasoning.
"""

from .base import (
    EngineError,
    EngineResult,
    ImagePayloadRejected,
    NoKeyAvailable,
    RateLimited,
    TextMessage,
)
from .text_deepseek import TextEngine
from .vision_gemini import VisionEngine

__all__ = [
    "EngineError",
    "EngineResult",
    "ImagePayloadRejected",
    "NoKeyAvailable",
    "RateLimited",
    "TextMessage",
    "TextEngine",
    "VisionEngine",
]
