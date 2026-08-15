"""Tool calls over a streamed completion (D-161).

`stream()` had no `tools` parameter while `complete()` did, so the chat box -
which streams - never handed the model its escalation tool. The system prompt
instructed it to use a tool it was never given, and the model did the only thing
available: it described the tool to the user by name and offered to explain how
to call it. Escalation was unreachable from the product's main surface for its
entire life, and nothing failed loudly enough to notice.

The hard part is not passing the argument. It is that a streamed tool call
arrives in fragments - the name in one chunk, the JSON arguments a few
characters at a time across later ones - so these tests are mostly about
reassembly.
"""

import pytest

from apps.ai.engines.text_openai_compatible import TextEngine


class _Function:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _ToolFragment:
    def __init__(self, index=0, name=None, arguments=None):
        self.index = index
        self.function = _Function(name, arguments)


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, delta=None, usage=None):
        self.choices = [_Choice(delta)] if delta is not None else []
        self.usage = usage


class _Usage:
    prompt_tokens = 120
    completion_tokens = 45


def engine_yielding(chunks, capture=None):
    """A TextEngine whose provider returns the given chunks."""
    engine = TextEngine(api_key="sk-test", model="test-model", base_url="https://example.test")

    class _Completions:
        def create(self, **kwargs):
            if capture is not None:
                capture.update(kwargs)
            return iter(chunks)

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    engine._client = lambda: _Client()
    return engine


def drain(engine, messages, **kwargs):
    return "".join(engine.stream(messages, **kwargs))


@pytest.fixture
def question():
    from apps.ai.engines import TextMessage

    return [TextMessage(role="user", content="my adobe password is wrong")]


# ------------------------------------------------------------- passing them --


def test_tools_reach_the_provider(question):
    """The whole bug in one assertion."""
    captured = {}
    engine = engine_yielding([_Chunk(_Delta(content="hello"))], capture=captured)
    tool = {"type": "function", "function": {"name": "escalate_via_email"}}

    drain(engine, question, tools=[tool])

    assert captured["tools"] == [tool]
    assert captured["stream"] is True


def test_no_tools_sends_none_not_an_empty_list(question):
    """Some providers reject `tools: []` outright rather than ignoring it."""
    captured = {}
    engine = engine_yielding([_Chunk(_Delta(content="hi"))], capture=captured)

    drain(engine, question)

    assert captured["tools"] is None


# --------------------------------------------------------------- reassembly --


def test_arguments_split_across_chunks_are_reassembled(question):
    """How a real provider sends it: the name once, then JSON a few characters
    at a time. Reading any single chunk gives unparseable fragments."""
    engine = engine_yielding(
        [
            _Chunk(_Delta(tool_calls=[_ToolFragment(name="escalate_via_email", arguments='{"su')])),
            _Chunk(_Delta(tool_calls=[_ToolFragment(arguments='bject": "Adobe')])),
            _Chunk(_Delta(tool_calls=[_ToolFragment(arguments=' portal locked"}')])),
        ]
    )

    drain(engine, question)

    assert engine.last_tool_calls == [
        {"name": "escalate_via_email", "arguments": '{"subject": "Adobe portal locked"}'}
    ]


def test_two_concurrent_calls_do_not_bleed_into_each_other(question):
    """Fragments interleave by index. Appending to one flat buffer would splice
    two argument strings into a single unparseable one."""
    engine = engine_yielding(
        [
            _Chunk(_Delta(tool_calls=[_ToolFragment(0, name="first", arguments='{"a":')])),
            _Chunk(_Delta(tool_calls=[_ToolFragment(1, name="second", arguments='{"b":')])),
            _Chunk(_Delta(tool_calls=[_ToolFragment(0, arguments="1}")])),
            _Chunk(_Delta(tool_calls=[_ToolFragment(1, arguments="2}")])),
        ]
    )

    drain(engine, question)

    assert engine.last_tool_calls == [
        {"name": "first", "arguments": '{"a":1}'},
        {"name": "second", "arguments": '{"b":2}'},
    ]


def test_content_and_a_tool_call_can_arrive_together(question):
    """A model may explain itself and escalate in the same turn. Losing either
    gives a bubble with no card, or a card with no explanation."""
    engine = engine_yielding(
        [
            _Chunk(_Delta(content="I'll pass this to your IT team. ")),
            _Chunk(_Delta(tool_calls=[_ToolFragment(name="escalate_via_email", arguments="{}")])),
            _Chunk(_Delta(content="They'll be in touch.")),
        ]
    )

    text = drain(engine, question)

    assert text == "I'll pass this to your IT team. They'll be in touch."
    assert engine.last_tool_calls[0]["name"] == "escalate_via_email"


def test_a_fragment_with_no_name_is_discarded(question):
    """A call whose name never arrived cannot be dispatched, and forwarding it
    as an anonymous call would look like a tool the caller does not recognise."""
    engine = engine_yielding(
        [_Chunk(_Delta(tool_calls=[_ToolFragment(arguments='{"orphan": true}')]))]
    )

    drain(engine, question)

    assert engine.last_tool_calls == []


def test_tool_calls_are_reset_between_streams(question):
    """The engine is constructed per call today, but a leaked list would attach
    one user's escalation to the next user's answer."""
    engine = engine_yielding(
        [_Chunk(_Delta(tool_calls=[_ToolFragment(name="escalate_via_email", arguments="{}")]))]
    )
    drain(engine, question)
    assert engine.last_tool_calls

    engine._client = engine_yielding([_Chunk(_Delta(content="just prose"))])._client
    drain(engine, question)

    assert engine.last_tool_calls == []


# ------------------------------------------------------------------ metering --


def test_usage_still_lands_when_a_tool_is_called(question):
    """D-110: no provider call without a meter reading. A turn that escalates is
    still a turn that was paid for."""
    engine = engine_yielding(
        [
            _Chunk(_Delta(tool_calls=[_ToolFragment(name="escalate_via_email", arguments="{}")])),
            _Chunk(usage=_Usage()),
        ]
    )

    drain(engine, question)

    assert engine.last_usage.prompt_tokens == 120
    assert engine.last_usage.completion_tokens == 45


def test_a_text_engine_still_refuses_an_image(question):
    """The engine contract (A-010) must survive the addition of tools: a text
    engine has no parameter capable of carrying an image, and `tools` is not a
    back door for one."""
    from apps.ai.engines.base import ImagePayloadRejected, TextMessage

    engine = engine_yielding([_Chunk(_Delta(content="x"))])

    with pytest.raises(ImagePayloadRejected):
        drain(
            engine,
            [TextMessage(role="user", content="data:image/png;base64,AAAA")],
            tools=[{"type": "function", "function": {"name": "escalate_via_email"}}],
        )
