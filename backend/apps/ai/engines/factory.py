"""Build an engine client from a ProviderKey (A-010).

The ONE place that maps provider -> client class. Adding a vendor means adding a
branch here, not touching the router, the ingestion pipeline or the chat code.

What this does NOT do is change the engine contract. A TEXT key gets a text
client - guarded by _assert_text_only - whichever vendor serves it. A VISION key
gets a vision client. The role/vendor split is the whole point: vendors are
configuration, roles are architecture.
"""

from __future__ import annotations

from .base import EngineError
from .text_deepseek import TextEngine
from .vision_gemini import VisionEngine as GeminiVisionEngine
from .vision_openai import OpenAICompatibleVisionEngine


def build_text_engine(key, api_key: str) -> TextEngine:
    """Every text provider speaks the OpenAI protocol, so there is one adapter.

    DeepSeek, OpenAI, Groq, OpenRouter, Together, Mistral, Ollama and Gemini's
    compatibility endpoint all land here.
    """
    base_url = key.resolved_base_url
    model = key.resolved_model

    if not base_url:
        raise EngineError(
            f"Key '{key.label}' has no base_url. A generic OpenAI-compatible "
            f"endpoint needs one (for example https://api.groq.com/openai/v1)."
        )
    if not model:
        raise EngineError(f"Key '{key.label}' has no model id configured.")

    return TextEngine(api_key, model=model, base_url=base_url)


def build_vision_engine(key, api_key: str):
    """Gemini uses its native SDK; everything else uses the OpenAI protocol."""
    model = key.resolved_model
    if not model:
        raise EngineError(f"Key '{key.label}' has no vision model id configured.")

    if key.uses_native_gemini:
        return GeminiVisionEngine(api_key, model=model)

    return OpenAICompatibleVisionEngine(api_key, model=model, base_url=key.resolved_base_url)


def build_engine(key, api_key: str):
    """Dispatch on the key's ROLE, then its provider."""
    from apps.ai.models import Engine

    if key.engine == Engine.TEXT:
        return build_text_engine(key, api_key)
    if key.engine == Engine.VISION:
        return build_vision_engine(key, api_key)
    raise EngineError(f"Unknown engine role {key.engine!r}.")
