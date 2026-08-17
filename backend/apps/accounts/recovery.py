"""Getting back into an account you are locked out of (D-176).

Two calls: ask for a code, then use it. Everything in between is about the fact
that this endpoint is reachable by anybody, needs no credentials, and sends
email - which makes it three attack surfaces at once:

* it can be used to find out who has an account, so it must never say
* it can be used to flood somebody's inbox, so it must be rate limited
* it can be brute-forced, so codes expire and die after a few wrong guesses

The response is identical whether or not the address exists. That single rule
costs nothing and removes the endpoint's value as a customer list.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.audit.models import Level, record
from apps.platformadmin import mail as platform_mail

from .models import PasswordResetCode

logger = logging.getLogger(__name__)

# Deliberately modest. A locked-out person needs one or two attempts, not
# twenty, and every extra send is somebody else's inbox if the address was
# guessed rather than owned.
MAX_PER_ADDRESS_PER_HOUR = 3
MAX_PER_IP_PER_HOUR = 10
COOLDOWN_SECONDS = 60

# The one thing this endpoint ever says. Identical for a real address and an
# invented one, so it cannot be used to test whether somebody is a customer.
GENERIC_REPLY = "If that address has an account, a reset code is on its way."

SUBJECT = "[MateAssist] Your password reset code"

BODY = """Somebody asked to reset the password for this MateAssist account.

Your code is:

    {code}

It expires in {minutes} minutes and can be used once.

If this was not you, nothing has changed - you can ignore this email. Somebody
knowing your address is not the same as them having access to your account.

--
Sent by MateAssist.
"""


def _generate_code() -> str:
    """Six digits, from `secrets`.

    Not `random`: this is a temporary password, and the default generator is
    seeded predictably enough to reconstruct a sequence from a few samples.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def _too_many(user, ip: str | None) -> bool:
    """Rate limits, checked before anything is sent.

    Per address AND per IP, because they stop different abuses: the first stops
    one person's inbox being buried, the second stops a script walking a list of
    addresses to find which ones exist by watching how long each takes.
    """
    hour_ago = timezone.now() - timedelta(hours=1)

    recent = PasswordResetCode.objects.filter(user=user, created_at__gte=hour_ago)
    if recent.count() >= MAX_PER_ADDRESS_PER_HOUR:
        return True

    newest = recent.order_by("-created_at").first()
    if newest and (timezone.now() - newest.created_at).total_seconds() < COOLDOWN_SECONDS:
        return True

    if ip:
        from_ip = PasswordResetCode.objects.filter(requested_ip=ip, created_at__gte=hour_ago)
        if from_ip.count() >= MAX_PER_IP_PER_HOUR:
            return True

    return False


def request_code(*, email: str, ip: str | None = None) -> dict:
    """Send a reset code, or quietly do nothing. Always answers the same.

    Never raises and never reports failure to the caller. A mail server error,
    an unknown address and a rate limit all produce the same reply, because any
    difference between them is information about who has an account.
    """
    address = (email or "").strip().lower()
    User = get_user_model()

    user = User.objects.filter(email=address, is_active=True).first()
    if user is None:
        # Logged, not answered. An operator investigating a support call needs
        # to see that a code was requested for an address that does not exist.
        logger.info("password reset requested for unknown address")
        return {"detail": GENERIC_REPLY}

    if _too_many(user, ip):
        record(
            "auth.reset.throttled",
            actor=user,
            level=Level.WARN,
            target=user.email,
            ip=ip or "",
        )
        return {"detail": GENERIC_REPLY}

    code = _generate_code()
    PasswordResetCode.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=PasswordResetCode.LIFETIME_MINUTES),
        requested_ip=ip or None,
    )

    result = platform_mail.send(
        to=user.email,
        subject=SUBJECT,
        body=BODY.format(code=code, minutes=PasswordResetCode.LIFETIME_MINUTES),
    )
    record(
        "auth.reset.requested",
        actor=user,
        level=Level.AUTH,
        target=user.email,
        ip=ip or "",
        delivered=result["sent"],
    )
    if not result["sent"]:
        # The user is told nothing different - saying "our mail is broken"
        # confirms the address exists. The operator sees it in the log.
        logger.error("reset code could not be delivered: %s", result["detail"])

    return {"detail": GENERIC_REPLY}


@transaction.atomic
def confirm_code(*, email: str, code: str, new_password: str, ip: str | None = None) -> dict:
    """Check a code and set the password. Returns {ok, detail}.

    The failure message is the same for a wrong code, an expired one and an
    unknown address - three states an attacker would otherwise use to learn
    whether they had the right address.
    """
    from apps.tenancy.provisioning import ProvisioningError, check_password_strength

    address = (email or "").strip().lower()
    failure = {"ok": False, "detail": "That code is not valid. Request a new one."}

    User = get_user_model()
    user = User.objects.filter(email=address, is_active=True).first()
    if user is None:
        return failure

    # select_for_update so two submissions of the same code cannot both pass
    # the used_at check before either writes it.
    entry = (
        PasswordResetCode.objects.select_for_update()
        .filter(user=user)
        .order_by("-created_at")
        .first()
    )
    if entry is None or not entry.is_live:
        return failure

    if not check_password((code or "").strip(), entry.code_hash):
        # Counted before returning, so guessing costs the attacker the code
        # rather than costing them nothing.
        entry.attempts += 1
        entry.save(update_fields=["attempts"])
        record(
            "auth.reset.failed",
            actor=user,
            level=Level.WARN,
            target=user.email,
            ip=ip or "",
            attempts=entry.attempts,
        )
        return failure

    try:
        check_password_strength(new_password, user)
    except ProvisioningError as exc:
        # A weak password does NOT consume the code. The person proved who they
        # are; making them start over because of a password rule is punishing
        # the wrong mistake.
        return {"ok": False, "detail": str(exc)}

    user.set_password(new_password)
    user.save(update_fields=["password"])

    entry.used_at = timezone.now()
    entry.save(update_fields=["used_at"])

    # Any other code for this user dies too. Two outstanding codes after a
    # successful reset is a second way in that nobody is watching.
    PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())

    revoked = _revoke_sessions(user)
    record(
        "auth.reset.completed",
        actor=user,
        level=Level.AUTH,
        target=user.email,
        ip=ip or "",
        sessions_revoked=revoked,
    )
    return {"ok": True, "detail": "Your password has been changed. Sign in with it now."}


def _revoke_sessions(user) -> int:
    """End every existing session for this account.

    The reason someone resets a password is often that somebody else has it. A
    reset that leaves the intruder's session alive changes the lock and leaves
    them inside the house.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        tokens = OutstandingToken.objects.filter(user=user)
        count = 0
        for token in tokens:
            _, created = BlacklistedToken.objects.get_or_create(token=token)
            count += int(created)
        return count
    except Exception:  # noqa: BLE001
        # Never let session cleanup fail the reset itself. The password is
        # already changed; a stale refresh token is a smaller problem than an
        # error page after a successful recovery.
        logger.exception("could not revoke sessions after password reset")
        return 0
