"""Escalation by email (A-008, D-124 to D-129).

MateAssist stores no tickets. When the agent cannot resolve an issue it compiles
the transcript and any image descriptions, and emails
them to the workspace's existing helpdesk.

The model never sends anything. It proposes; the authenticated user confirms.
That is the same human-in-the-loop rule the ticket flow had, and it matters more
here - an email leaves the system and cannot be recalled.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.audit.models import Level, record
from apps.tenancy import mail

from .models import Message

logger = logging.getLogger(__name__)

BODY_TEMPLATE = """A user could not resolve this issue with MateAssist and asked for a human.

WORKSPACE   {tenant}
REPORTED BY {user}
CATEGORY    {category}
RAISED      {timestamp}

--- SUMMARY -------------------------------------------------------------
{summary}

--- TRANSCRIPT ----------------------------------------------------------
{transcript}

--
Sent by MateAssist. Replying to this email reaches the user directly.
"""


def _render_transcript(messages) -> str:
    lines = []
    for message in messages:
        who = "User" if message.role == "user" else "MateAssist"
        lines.append(f"[{message.created_at:%H:%M}] {who}: {message.text}".rstrip())
        if message.attachment_description:
            lines.append(
                f"          (screenshot attached, transcribed as: "
                f"{message.attachment_description[:400]})"
            )
    return "\n\n".join(lines) or "(no transcript)"


# The email used to carry a "WHAT THE ASSISTANT CONSULTED" block listing the
# runbooks behind each answer. D-141 removed it: the engineer receiving an
# escalation maintains those runbooks and does not need their titles recited,
# and the transcript already shows what the assistant actually said - which is
# the part they act on.
#
# Citations are still stored on every message, so a platform admin can still
# answer "which document produced this?" when an answer turns out to be wrong.


def resolve_recipient(tenant) -> str:
    """Per-tenant address, falling back to the platform default (D-128).

    A tenant's escalations must never reach another tenant's helpdesk, so this
    reads from the tenant and never from a request parameter.
    """
    address = (getattr(tenant, "support_email", "") or "").strip()
    return address or getattr(settings, "DEFAULT_SUPPORT_EMAIL", "")


def send_escalation(*, tenant, user, conversation, proposal: dict) -> dict:
    """Compile and send. Returns a result dict; never raises to the caller."""
    recipient = resolve_recipient(tenant)
    if not recipient:
        return {
            "sent": False,
            "detail": (
                "No support email is configured for this workspace. "
                "Ask your administrator to set one."
            ),
        }

    # all_objects, not the tenant-scoped manager. The conversation was already
    # fetched under tenant scoping, so authorisation is settled - but the scoped
    # manager reads a ContextVar, and a caller that has armed the DB session
    # without the Python context (a Celery task, a management command) would get
    # an EMPTY queryset and silently send an escalation with no transcript.
    # A blank transcript is worse than an error: the helpdesk gets a ticket with
    # nothing in it and no sign anything went wrong.
    messages = list(
        Message.all_objects.filter(conversation=conversation).order_by("created_at", "id")
    )
    if not messages:
        return {"sent": False, "detail": "This conversation has no messages to escalate."}

    subject = (proposal.get("subject") or "IT issue escalated from MateAssist").strip()

    body = BODY_TEMPLATE.format(
        tenant=tenant.name,
        user=getattr(user, "display_name", None) or getattr(user, "email", "unknown"),
        category=proposal.get("category") or "Other",
        timestamp=timezone.now().strftime("%Y-%m-%d %H:%M UTC"),
        summary=proposal.get("summary") or "(no summary provided)",
        transcript=_render_transcript(messages),
    )

    # Sent through the WORKSPACE's own mail server when it has one (D-154).
    # A message whose From address says @customer.com but which leaves the
    # platform's server fails their SPF record and lands in spam - so the one
    # email that matters is the one that silently disappears.
    email = EmailMessage(
        subject=f"[MateAssist] {subject}",
        body=body,
        from_email=mail.from_address(tenant),
        to=[recipient],
        # Replying reaches the user rather than a no-reply void.
        reply_to=[user.email] if getattr(user, "email", None) else None,
        connection=mail.connection_for(tenant),
    )

    try:
        email.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001
        logger.exception("escalation email failed for conversation %s", conversation.pk)
        record(
            "chat.escalate.failed",
            tenant=tenant,
            actor=user,
            level=Level.ERROR,
            target=subject,
            conversation_id=conversation.pk,
            error=str(exc)[:300],
        )
        return {"sent": False, "detail": f"The email could not be sent: {exc}"}

    conversation.escalated_at = timezone.now()
    conversation.resolved = False
    conversation.save(update_fields=["escalated_at", "resolved", "updated_at"])

    # D-129: the escalation is recorded as metadata. The transcript itself is
    # not duplicated into the audit log - it has already left in the email, and
    # a second copy is a second thing to protect.
    record(
        "chat.escalate",
        tenant=tenant,
        actor=user,
        target=subject,
        conversation_id=conversation.pk,
        recipient=recipient,
        category=proposal.get("category") or "Other",
        messages=len(messages),
    )
    return {"sent": True, "recipient": recipient, "subject": subject}
