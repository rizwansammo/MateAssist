"""What a user is allowed to see when an engine call fails (D-135).

The failure this guards against is not a crash - it is a leak that renders
perfectly. A raw provider error reached a helpdesk user's chat window carrying
the vendor name, the workspace's quota position, Google's documentation URL and
Python dict formatting. It looked like a working error message.
"""

import pytest

from apps.ai import user_messages
from apps.ai.engines import EngineError, ImagePayloadRejected, NoKeyAvailable, RateLimited
from apps.metering.budgets import BudgetExceeded

# The exact text a real Gemini 429 produced in the browser.
REAL_PROVIDER_ERROR = (
    "Error code: 429 - [{'error': {'code': 429, 'message': 'You exceeded your "
    "current quota, please check your plan and billing details. For more "
    "information on this error, head to: https://ai.google.dev/gemini-api/docs/"
    "rate-limits."
)

LEAKY_FRAGMENTS = (
    "gemini",
    "google",
    "deepseek",
    "openai",
    "groq",
    "anthropic",
    "quota",
    "429",
    "http",
    "{",
    "traceback",
)


def assert_safe(message: str) -> None:
    """No vendor, no quota position, no URL, no Python formatting.

    Deliberately does NOT require the word "MateAssist": the budget message is
    about the workspace's own limit, not about the assistant, and forcing the
    product name into it would make it read worse for no gain.
    """
    lowered = message.lower()
    for fragment in LEAKY_FRAGMENTS:
        assert fragment not in lowered, f"user-facing message leaked {fragment!r}: {message}"


# ------------------------------------------------------------- mapping ------


def test_a_rate_limit_becomes_the_busy_message():
    message = user_messages.for_exception(RateLimited(REAL_PROVIDER_ERROR))

    assert message == user_messages.BUSY
    assert_safe(message)


def test_an_exhausted_pool_still_reads_as_busy():
    """The router re-raises as RateLimited when every key is throttled, so the
    user is told to retry rather than that something is broken."""
    exhausted = RateLimited("TEXT pool exhausted after 3 attempt(s): " + REAL_PROVIDER_ERROR)
    assert user_messages.for_exception(exhausted) == user_messages.BUSY


def test_no_configured_key_is_not_a_rate_limit():
    """Different cause, different sentence: retrying will not help here."""
    message = user_messages.for_exception(NoKeyAvailable("No usable TEXT key"))

    assert message == user_messages.UNAVAILABLE
    assert message != user_messages.BUSY
    assert_safe(message)


def test_a_budget_stop_tells_the_user_who_can_fix_it():
    from apps.tenancy.models import Tenant

    exc = BudgetExceeded(tenant=Tenant(name="Alpha"), spent=10, cap=5)
    message = user_messages.for_exception(exc)

    assert message == user_messages.BUDGET
    assert "administrator" in message.lower(), "the user cannot lift their own cap"
    assert_safe(message)


def test_an_unknown_failure_falls_back_to_generic_not_to_its_own_text():
    """A new exception type must never default to exposing itself."""

    class SomethingNew(Exception):
        pass

    message = user_messages.for_exception(SomethingNew(REAL_PROVIDER_ERROR))

    assert message == user_messages.GENERIC
    assert_safe(message)


def test_every_defined_message_is_safe():
    for message in (
        user_messages.BUSY,
        user_messages.UNAVAILABLE,
        user_messages.BUDGET,
        user_messages.GENERIC,
    ):
        assert_safe(message)


def test_engine_failures_speak_as_MateAssist():
    """When the assistant itself is the thing that failed, it says so by name -
    otherwise the user is left guessing which system broke."""
    for message in (user_messages.BUSY, user_messages.UNAVAILABLE, user_messages.GENERIC):
        assert "MateAssist" in message


def test_the_busy_wording_is_the_agreed_sentence():
    assert user_messages.BUSY == (
        "MateAssist is handling a lot of requests right now. Please try again in a moment."
    )


def test_specific_types_win_over_the_engine_error_base():
    """RateLimited and NoKeyAvailable both subclass EngineError. If the generic
    branch were checked first, every failure would read the same."""
    assert user_messages.for_exception(RateLimited("x")) != user_messages.GENERIC
    assert user_messages.for_exception(NoKeyAvailable("x")) != user_messages.GENERIC
    assert user_messages.for_exception(EngineError("x")) == user_messages.GENERIC
    assert user_messages.for_exception(ImagePayloadRejected("x")) == user_messages.GENERIC


# -------------------------------------------------------------- report ------


# Both aliases: a platform-scope audit row (tenant=None) is written through the
# `admin` connection, because RLS correctly refuses a null-tenant insert while a
# tenant context is armed. See the note in audit.record.
@pytest.mark.django_db(databases=["default", "admin"])
def test_report_keeps_the_real_error_for_operators():
    """The detail must survive somewhere an admin can reach - System Logs -
    even though the user never sees it."""
    from apps.audit.models import AuditEvent

    returned = user_messages.report(RateLimited(REAL_PROVIDER_ERROR), context="chat.stream")

    assert returned == user_messages.BUSY

    # Read back on the SAME alias it was written through. `admin` is a separate
    # connection, so its row is invisible to `default` until committed - reading
    # from the wrong one fails for a reason that has nothing to do with the code
    # under test.
    event = (
        AuditEvent.objects.using("admin")
        .filter(action="engine.error")
        .order_by("-created_at")
        .first()
    )
    assert event is not None
    assert event.target == "chat.stream"
    assert event.metadata["error_type"] == "RateLimited"
    assert "429" in event.metadata["detail"], "operators keep the diagnostic detail"
