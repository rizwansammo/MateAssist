"""The engine contract (D-040 to D-043).

The product's central safety claim is that images reach Gemini and stop there,
and only the text Gemini returns continues to DeepSeek. These tests attack that
claim from every direction a real bug would take.

No network and no API key is needed: the guard runs before any client is
constructed, which is itself part of the design.
"""

import pytest

from apps.ai.engines import ImagePayloadRejected, TextEngine, TextMessage
from apps.ai.engines.text_openai_compatible import _assert_text_only
from apps.ai.engines.vision_gemini import VisionEngine

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def engine():
    return TextEngine(api_key="not-used-the-guard-runs-first")


# ------------------------------------------------------- structural shape ---


def test_text_message_has_no_field_that_can_carry_an_image():
    """The type signature is the first line of defence: there is no shape a
    TextMessage can take that holds an image."""
    fields = set(TextMessage.__dataclass_fields__)

    assert fields == {"role", "content", "name", "tool_call_id"}
    assert TextMessage.__dataclass_fields__["content"].type in (str, "str")


def test_text_engine_exposes_no_image_parameter():
    """complete() and stream() must not grow an image/attachment/parts kwarg."""
    import inspect

    for method in (TextEngine.complete, TextEngine.stream):
        params = set(inspect.signature(method).parameters)
        forbidden = {"image", "images", "image_bytes", "attachments", "parts", "files"}
        assert not (params & forbidden), f"{method.__name__} gained an image parameter: {params}"


# ------------------------------------------------------------ the guard -----


def test_raw_bytes_are_rejected():
    message = TextMessage(role="user", content=PNG_BYTES)  # type: ignore[arg-type]
    with pytest.raises(ImagePayloadRejected, match="binary"):
        _assert_text_only([message])


def test_openai_style_parts_list_is_rejected():
    """The canonical way an image gets smuggled into a chat API."""
    smuggled = {
        "role": "user",
        "content": [
            {"type": "text", "text": "what is this?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
        ],
    }
    with pytest.raises(ImagePayloadRejected, match="TextMessage"):
        _assert_text_only([smuggled])


def test_data_uri_inside_a_string_is_rejected():
    """Even correctly typed as str, a base64 image is still an image."""
    message = TextMessage(role="user", content="here: data:image/png;base64,iVBORw0KGgo=")
    with pytest.raises(ImagePayloadRejected, match="data:image/"):
        _assert_text_only([message])


@pytest.mark.parametrize("marker", ["image_url", "inline_data", "b64_json"])
def test_provider_image_field_names_are_rejected(marker):
    message = TextMessage(role="user", content=f'{{"{marker}": "..."}}')
    with pytest.raises(ImagePayloadRejected):
        _assert_text_only([message])


def test_guard_runs_before_any_network_call():
    """The rejection must happen before a client is built, so a misuse cannot
    leak an image even when the API key is valid and the network is up."""
    with pytest.raises(ImagePayloadRejected):
        engine().complete([TextMessage(role="user", content=PNG_BYTES)])  # type: ignore[arg-type]


def test_guard_inspects_every_message_not_just_the_first():
    messages = [
        TextMessage(role="system", content="You are a helpdesk assistant."),
        TextMessage(role="user", content="my printer is broken"),
        TextMessage(role="user", content="data:image/jpeg;base64,/9j/4AAQ"),
    ]
    with pytest.raises(ImagePayloadRejected, match=r"messages\[2\]"):
        _assert_text_only(messages)


# --------------------------------------------------------- the happy path ---


def test_ordinary_text_passes():
    messages = [
        TextMessage(role="system", content="You are a helpdesk assistant."),
        TextMessage(role="user", content="VPN drops when I join Teams calls."),
    ]
    _assert_text_only(messages)  # must not raise


def test_gemini_description_is_what_reaches_deepseek():
    """The intended handoff: Gemini returns prose, and that prose - never the
    bytes - is what the reasoning engine sees (D-042)."""
    description = (
        "Windows dialog titled 'GlobalProtect', message 'no network connectivity', "
        "error code 0x80070035, OK and Cancel buttons visible."
    )
    messages = [TextMessage(role="user", content=f"[User attached a screenshot: {description}]")]

    _assert_text_only(messages)  # must not raise
    assert "0x80070035" in messages[0].content


# --------------------------------------------------------- vision engine ----


def test_vision_engine_is_the_only_module_taking_image_bytes():
    import inspect

    params = inspect.signature(VisionEngine.describe).parameters
    assert "image_bytes" in params
    assert "mime_type" in params


def test_vision_engine_rejects_non_image_mime():
    from apps.ai.engines import EngineError

    with pytest.raises(EngineError, match="Unsupported image type"):
        VisionEngine(api_key="x").describe(PNG_BYTES, mime_type="application/pdf")


def test_vision_engine_rejects_non_bytes():
    from apps.ai.engines import EngineError

    with pytest.raises(EngineError, match="raw image bytes"):
        VisionEngine(api_key="x").describe("not bytes", mime_type="image/png")  # type: ignore[arg-type]
