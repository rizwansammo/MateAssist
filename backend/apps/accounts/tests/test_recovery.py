"""Password recovery by emailed code (D-176).

This endpoint is reachable by anybody, needs no credentials, and sends email.
That makes it three things at once - a way to learn who has an account, a way to
flood an inbox, and something to brute-force - so nearly every test here is
about a way it could be abused rather than the happy path.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import recovery
from apps.accounts.models import PasswordResetCode
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
NEW = "Str0ng!Passphrase42"

REQUEST_URL = "/api/v1/auth/password-reset/"
CONFIRM_URL = "/api/v1/auth/password-reset/confirm/"
HOST = "alpha.localhost"


@pytest.fixture(autouse=True)
def outbox(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox.clear()
    return mail.outbox


@pytest.fixture
def user():
    tenant = Tenant.objects.create(name="Alpha", slug="alpha")
    person = User.objects.create_user("rizwan@alpha.test", PASSWORD)
    set_db_tenant(tenant.id)
    Membership.all_objects.create(user=person, tenant=tenant, role=Role.END_USER)
    set_db_tenant(None)
    return person


def client():
    api = APIClient()
    api.defaults["HTTP_HOST"] = HOST
    return api


def code_from_email(outbox) -> str:
    """The six digits out of the message body."""
    import re

    return re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)


# --------------------------------------------------------------- requesting --


def test_a_code_is_emailed_to_a_real_address(user, outbox):
    response = client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")

    assert response.status_code == 200
    assert len(outbox) == 1
    assert outbox[0].to == ["rizwan@alpha.test"]
    assert len(code_from_email(outbox)) == 6


def test_an_unknown_address_gets_the_same_answer_and_no_email(user, outbox):
    """The headline protection. A different reply for an unknown address turns
    this endpoint into a way to test who is a customer."""
    known = client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")
    unknown = client().post(REQUEST_URL, {"email": "nobody@nowhere.test"}, format="json")

    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data
    assert len(outbox) == 1  # only the real one was sent


def test_a_deactivated_account_gets_no_code(user, outbox):
    """Recovery must not undo a deactivation - that would be a way back in for
    somebody an administrator deliberately removed."""
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")

    assert response.status_code == 200
    assert outbox == []


def test_the_code_is_hashed_not_stored(user, outbox):
    """A plaintext code in a database dump is an account."""
    client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")

    code = code_from_email(outbox)
    entry = PasswordResetCode.objects.get()

    assert code not in entry.code_hash
    assert entry.code_hash != code


def test_broken_mail_does_not_change_the_reply(user, outbox, monkeypatch):
    """Saying "our mail server failed" confirms the address exists."""
    from apps.platformadmin import mail as platform_mail

    monkeypatch.setattr(
        platform_mail, "send", lambda **kwargs: {"sent": False, "detail": "smtp exploded"}
    )

    response = client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")

    assert response.status_code == 200
    assert "smtp" not in str(response.data).lower()


# ------------------------------------------------------------ rate limiting --


def test_a_second_request_within_a_minute_sends_nothing(user, outbox):
    """Otherwise a held-down button buries somebody's inbox."""
    client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")
    client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")

    assert len(outbox) == 1


def test_an_address_is_capped_per_hour(user, outbox):
    for _ in range(6):
        # Age each one past the cooldown so the hourly cap is what is being
        # tested, not the 60-second gap.
        client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")
        PasswordResetCode.objects.update(created_at=timezone.now() - timedelta(minutes=5))

    assert len(outbox) <= recovery.MAX_PER_ADDRESS_PER_HOUR


def test_throttling_still_returns_the_same_reply(user, outbox):
    first = client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")
    second = client().post(REQUEST_URL, {"email": "rizwan@alpha.test"}, format="json")

    assert first.data == second.data


# --------------------------------------------------------------- confirming --


def request_code(user):
    client().post(REQUEST_URL, {"email": user.email}, format="json")
    return code_from_email(mail.outbox)


def test_the_right_code_changes_the_password(user, outbox):
    code = request_code(user)

    response = client().post(
        CONFIRM_URL,
        {"email": user.email, "code": code, "new_password": NEW},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW)


def test_a_wrong_code_is_refused_and_counted(user, outbox):
    request_code(user)

    response = client().post(
        CONFIRM_URL,
        {"email": user.email, "code": "000000", "new_password": NEW},
        format="json",
    )

    assert response.status_code == 400
    assert PasswordResetCode.objects.get().attempts == 1
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_a_code_dies_after_five_wrong_guesses(user, outbox):
    """Six digits is a million guesses, and a patient script would find one."""
    code = request_code(user)

    for _ in range(5):
        client().post(
            CONFIRM_URL,
            {"email": user.email, "code": "000000", "new_password": NEW},
            format="json",
        )

    response = client().post(
        CONFIRM_URL, {"email": user.email, "code": code, "new_password": NEW}, format="json"
    )

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_an_expired_code_is_refused(user, outbox):
    code = request_code(user)
    PasswordResetCode.objects.update(expires_at=timezone.now() - timedelta(minutes=1))

    response = client().post(
        CONFIRM_URL, {"email": user.email, "code": code, "new_password": NEW}, format="json"
    )

    assert response.status_code == 400


def test_a_code_cannot_be_used_twice(user, outbox):
    """The second use is somebody who read the first person's email."""
    code = request_code(user)
    client().post(
        CONFIRM_URL, {"email": user.email, "code": code, "new_password": NEW}, format="json"
    )

    response = client().post(
        CONFIRM_URL,
        {"email": user.email, "code": code, "new_password": "An0ther!Passphrase9"},
        format="json",
    )

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(NEW)


def test_a_wrong_code_and_an_unknown_address_read_identically(user, outbox):
    request_code(user)

    wrong = client().post(
        CONFIRM_URL, {"email": user.email, "code": "000000", "new_password": NEW}, format="json"
    )
    unknown = client().post(
        CONFIRM_URL,
        {"email": "nobody@nowhere.test", "code": "000000", "new_password": NEW},
        format="json",
    )

    assert wrong.data == unknown.data


def test_a_weak_password_does_not_burn_the_code(user, outbox):
    """The person proved who they are. Making them start over because of a
    password rule punishes the wrong mistake."""
    code = request_code(user)

    weak = client().post(
        CONFIRM_URL, {"email": user.email, "code": code, "new_password": "1234"}, format="json"
    )
    assert weak.status_code == 400

    good = client().post(
        CONFIRM_URL, {"email": user.email, "code": code, "new_password": NEW}, format="json"
    )
    assert good.status_code == 200


def test_an_older_code_dies_when_a_newer_one_is_used(user, outbox):
    """Two live codes after a reset is a second way in that nobody is
    watching."""
    request_code(user)
    PasswordResetCode.objects.update(created_at=timezone.now() - timedelta(minutes=5))
    second = request_code(user)

    client().post(
        CONFIRM_URL, {"email": user.email, "code": second, "new_password": NEW}, format="json"
    )

    assert PasswordResetCode.objects.filter(used_at__isnull=True).count() == 0


def test_other_sessions_are_revoked(user, outbox):
    """The reason someone resets is often that somebody else has the password.
    Leaving that session alive changes the lock with the intruder inside."""
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    RefreshToken.for_user(user)
    assert OutstandingToken.objects.filter(user=user).exists()

    code = request_code(user)
    client().post(
        CONFIRM_URL, {"email": user.email, "code": code, "new_password": NEW}, format="json"
    )

    assert BlacklistedToken.objects.filter(token__user=user).exists()


def test_recovery_needs_no_authentication(user, outbox):
    """The person cannot sign in - that is the whole problem. Both endpoints
    must work with no credentials at all."""
    api = APIClient()
    api.defaults["HTTP_HOST"] = HOST

    assert api.post(REQUEST_URL, {"email": user.email}, format="json").status_code == 200
    assert (
        api.post(
            CONFIRM_URL,
            {"email": user.email, "code": code_from_email(mail.outbox), "new_password": NEW},
            format="json",
        ).status_code
        == 200
    )
