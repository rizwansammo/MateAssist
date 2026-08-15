"""Outbound mail, per workspace (D-154).

Escalations leave FROM the workspace, using the workspace's own mail server,
because deliverability depends on it. An email whose From address says
`@customer.com` but which leaves a server their SPF record does not authorise is
filed as spam - and the one message that matters, an unresolved problem reaching
a human, is exactly the one that disappears.

A workspace that has not configured anything falls back to the platform's own
settings, so escalation keeps working out of the box.
"""

from __future__ import annotations

import logging
from email.utils import formataddr

from django.conf import settings
from django.core.mail import get_connection

logger = logging.getLogger(__name__)


def connection_for(tenant):
    """An SMTP connection belonging to this workspace, or the platform default.

    Returning None would be simpler, but callers would then have to remember to
    handle it; returning Django's default connection means the caller has one
    code path and the fallback is invisible.
    """
    if tenant is None or not tenant.has_smtp:
        return get_connection()  # platform default from settings

    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=tenant.smtp_host,
        port=tenant.smtp_port,
        username=tenant.smtp_username or None,
        password=tenant.reveal_smtp_password() or None,
        use_tls=tenant.smtp_use_tls,
        # TLS and SSL are mutually exclusive in Django's backend, and passing
        # both raises rather than picking one. 465 is implicit SSL by
        # convention; everything else negotiates with STARTTLS.
        use_ssl=(not tenant.smtp_use_tls and tenant.smtp_port == 465),
        fail_silently=False,
        timeout=20,
    )


def from_address(tenant) -> str:
    """The From header for mail this workspace sends, name included (D-162).

    Falls back to the platform address, which is correct for a workspace with no
    mail server of its own - and wrong to use alongside a workspace host, since
    that mismatch is precisely what fails SPF.

    `formataddr` rather than an f-string: it quotes a name containing a comma or
    a full stop and RFC-2047 encodes anything non-ASCII. "Smith, Jones IT"
    interpolated raw would be parsed as two recipients, and an accented name
    would arrive as mojibake or be rejected outright.
    """
    if tenant is None or not tenant.smtp_from_email:
        return settings.DEFAULT_FROM_EMAIL

    name = (tenant.smtp_from_name or tenant.name or "").strip()
    return formataddr((name, tenant.smtp_from_email)) if name else tenant.smtp_from_email


def send_test(tenant, recipient: str) -> dict:
    """Send a one-line message so an administrator can prove the settings work.

    Without this the first test of a mail configuration is a real user's failed
    escalation, discovered when nobody answers them.
    """
    from django.core.mail import EmailMessage

    try:
        message = EmailMessage(
            subject="[MateAssist] Test message",
            body=(
                f"This is a test from MateAssist for {tenant.name}.\n\n"
                "If you received it, escalation emails from this workspace will "
                "reach your helpdesk.\n"
            ),
            from_email=from_address(tenant),
            to=[recipient],
            connection=connection_for(tenant),
        )
        message.send(fail_silently=False)
        return {"sent": True, "detail": f"Sent to {recipient}."}
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMTP test failed for tenant %s: %s", tenant.pk, exc)
        # The provider's message is genuinely useful HERE, unlike in the chat
        # (D-135): the reader is an administrator debugging their own mail
        # server, and "authentication failed" is the whole answer.
        return {"sent": False, "detail": str(exc)[:300]}
