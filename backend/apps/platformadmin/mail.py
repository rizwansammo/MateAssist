"""Mail sent by MateAssist itself (D-175).

Strictly separate from `apps.tenancy.mail`, which sends a customer's escalations
through the customer's own server. This sends OUR mail - password reset codes,
email-change confirmations - and must never travel over a tenant's connection.
Account recovery for the platform cannot depend on infrastructure a customer
controls, or on that customer's mailbox staying paid for.

Falls back to Django's configured backend when nothing is saved, which on a
fresh deployment is the console backend: mail is printed to the log and sent
nowhere. That is a safe default and a useless one, which is why the settings
page has a test button.
"""

from __future__ import annotations

import logging
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

logger = logging.getLogger(__name__)


def _settings():
    from .models import PlatformSettings

    return PlatformSettings.load()


def connection():
    """An SMTP connection for platform mail, or Django's default.

    Returning the default rather than None means callers have one code path and
    the fallback is invisible to them.
    """
    config = _settings()
    if not config.is_configured:
        return get_connection()

    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username or None,
        password=config.reveal_smtp_password() or None,
        use_tls=config.smtp_use_tls,
        # Mutually exclusive in Django's backend - passing both raises rather
        # than picking one. 465 is implicit SSL by convention.
        use_ssl=(not config.smtp_use_tls and config.smtp_port == 465),
        fail_silently=False,
        timeout=20,
    )


def from_address() -> str:
    """The From header on platform mail.

    `formataddr` rather than an f-string, so a name containing a comma is quoted
    instead of being parsed as two recipients.
    """
    config = _settings()
    if not config.from_email:
        return settings.DEFAULT_FROM_EMAIL

    name = (config.from_name or "MateAssist").strip()
    return formataddr((name, config.from_email)) if name else config.from_email


def send(*, to: str, subject: str, body: str) -> dict:
    """Send one message. Never raises.

    Returns {sent, detail}. Auth mail failing must not take down the request
    that triggered it - a reset endpoint that 500s tells an attacker more than
    it tells the locked-out user.
    """
    try:
        EmailMessage(
            subject=subject,
            body=body,
            from_email=from_address(),
            to=[to],
            connection=connection(),
        ).send(fail_silently=False)
        return {"sent": True, "detail": f"Sent to {to}."}
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform mail failed: %s", exc)
        # The provider's own message is useful HERE, unlike in the chat (D-135):
        # the reader is the platform owner debugging their own mail server, and
        # "username and password not accepted" is the whole answer.
        return {"sent": False, "detail": str(exc)[:300]}


TEST_SUBJECT = "[MateAssist] Platform mail is working"

TEST_BODY = """This is a test from your MateAssist platform settings.

If you received it, password reset codes and account emails will reach you.

--
Sent by MateAssist.
"""
