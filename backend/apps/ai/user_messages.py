"""What a user is allowed to see when an engine call fails (D-135).

A provider's error text is written for the developer holding the API key, not
for a helpdesk user. Passing it through leaks three things at once: which vendor
serves the role, the workspace's quota position, and raw Python formatting -

    Error code: 429 - [{'error': {'code': 429, 'message': 'You exceeded your
    current quota, please check your plan and billing details...'

None of that helps someone whose laptop will not connect to the VPN, and the
vendor name contradicts the product's own identity (A-010 makes the vendor a
configuration choice, so any message naming one is wrong the moment it changes).

So the mapping is by EXCEPTION TYPE, never by string matching, and the real
error goes to the log and the audit trail where an operator can reach it.
"""

from __future__ import annotations

import logging

from apps.metering.budgets import BudgetExceeded

from .engines import EngineError, ImagePayloadRejected, NoKeyAvailable, RateLimited

logger = logging.getLogger(__name__)

BUSY = "MateAssist is handling a lot of requests right now. Please try again in a moment."
UNAVAILABLE = "MateAssist can't reach the assistant right now. Your IT team has been notified."
BUDGET = (
    "This workspace has reached its monthly usage limit. "
    "Contact your IT administrator to continue."
)
GENERIC = "MateAssist couldn't complete that request. Please try again."

# Order matters: RateLimited and NoKeyAvailable are both EngineError subclasses,
# so the specific types have to be checked first.
_BY_TYPE: tuple[tuple[type[BaseException], str], ...] = (
    (BudgetExceeded, BUDGET),
    (RateLimited, BUSY),
    (NoKeyAvailable, UNAVAILABLE),
    (ImagePayloadRejected, GENERIC),
    (EngineError, GENERIC),
)


def for_exception(exc: BaseException) -> str:
    """The safe, user-facing sentence for this failure.

    Falls through to GENERIC for anything unrecognised - a new exception type
    must never default to exposing its own text.
    """
    for exception_type, message in _BY_TYPE:
        if isinstance(exc, exception_type):
            return message
    return GENERIC


def report(exc: BaseException, *, context: str, tenant=None, user=None) -> str:
    """Record the real failure, return the safe one.

    The operator-facing detail lands in two places: the application log for
    debugging, and an AuditEvent so a platform admin can see it in System Logs
    without shell access. The user gets the sentence.
    """
    logger.warning("%s failed: %s", context, exc, exc_info=True)

    from apps.audit.models import Level, record

    record(
        "engine.error",
        tenant=tenant,
        actor=user,
        level=Level.ERROR,
        target=context,
        error_type=type(exc).__name__,
        # Truncated because provider errors can be enormous, and this is a
        # diagnostic breadcrumb rather than a full trace - the log has that.
        detail=str(exc)[:500],
    )
    return for_exception(exc)
