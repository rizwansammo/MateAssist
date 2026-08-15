"""Editing your own account (D-158).

Two endpoints, both scoped to request.user with no id anywhere in the URL. That
is the whole authorisation model, so most of what follows is an attempt to reach
somebody else's account through them anyway.

Email changes are trusted as typed - verification was considered and declined -
so the guard is the current password. These tests pin that guard, because it is
the only thing standing between a borrowed session and a stolen account.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
HOST = "alpha.localhost"

ACCOUNT = "/api/v1/account/"
PASSWORD_URL = "/api/v1/account/password/"


@pytest.fixture
def world():
    tenant = Tenant.objects.create(name="Alpha", slug="alpha")
    alice = User.objects.create_user("alice@alpha.test", PASSWORD, full_name="Alice Adams")
    bob = User.objects.create_user("bob@alpha.test", PASSWORD, full_name="Bob Brown")

    set_db_tenant(tenant.id)
    Membership.all_objects.create(user=alice, tenant=tenant, role=Role.END_USER)
    Membership.all_objects.create(user=bob, tenant=tenant, role=Role.END_USER)
    set_db_tenant(None)

    client = APIClient()
    client.force_authenticate(user=alice)
    client.defaults["HTTP_HOST"] = HOST
    return {"client": client, "alice": alice, "bob": bob, "tenant": tenant}


# -------------------------------------------------------------- reading it --


def test_a_user_can_see_their_own_email(world):
    """The gap that started this: the address existed on every response and was
    rendered nowhere, so nobody could check what theirs was, let alone fix it."""
    response = world["client"].get(ACCOUNT, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.data["email"] == "alice@alpha.test"
    assert response.data["full_name"] == "Alice Adams"


def test_the_account_endpoint_never_returns_a_password(world):
    body = str(world["client"].get(ACCOUNT, HTTP_HOST=HOST).data)
    assert "password" not in body.lower()


def test_anonymous_users_are_refused(world):
    client = APIClient()
    assert client.get(ACCOUNT, HTTP_HOST=HOST).status_code in (401, 403)


# -------------------------------------------------------------- editing it --


def test_a_name_change_needs_no_password(world):
    """Changing a display name cannot be used to take anything, so demanding a
    password for it is friction with no security to show for it."""
    response = world["client"].patch(
        ACCOUNT, {"full_name": "Alice A. Adams", "job_title": "IT Lead"}, format="json"
    )

    assert response.status_code == 200
    world["alice"].refresh_from_db()
    assert world["alice"].full_name == "Alice A. Adams"
    assert world["alice"].job_title == "IT Lead"


def test_changing_the_email_requires_the_current_password(world):
    """The headline guard. Email is the login identity: without this, anyone who
    reaches an open session moves the account to their own address and the owner
    can never sign in again."""
    response = world["client"].patch(ACCOUNT, {"email": "attacker@evil.test"}, format="json")

    assert response.status_code == 400
    assert "current_password" in response.data
    world["alice"].refresh_from_db()
    assert world["alice"].email == "alice@alpha.test"


def test_a_wrong_current_password_does_not_change_the_email(world):
    response = world["client"].patch(
        ACCOUNT,
        {"email": "attacker@evil.test", "current_password": "not-the-password"},
        format="json",
    )

    assert response.status_code == 400
    world["alice"].refresh_from_db()
    assert world["alice"].email == "alice@alpha.test"


def test_the_email_changes_when_the_password_is_right(world):
    response = world["client"].patch(
        ACCOUNT, {"email": "alice.adams@alpha.test", "current_password": PASSWORD}, format="json"
    )

    assert response.status_code == 200
    world["alice"].refresh_from_db()
    assert world["alice"].email == "alice.adams@alpha.test"


def test_the_new_email_is_normalised_to_lowercase(world):
    """The manager lowercases on create. Without the same treatment here,
    `Alice@x.com` becomes a second identity that the login form, which
    lowercases what it is given, can never match."""
    world["client"].patch(
        ACCOUNT, {"email": "Alice.Adams@Alpha.Test", "current_password": PASSWORD}, format="json"
    )

    world["alice"].refresh_from_db()
    assert world["alice"].email == "alice.adams@alpha.test"


def test_an_email_already_in_use_is_refused(world):
    """Uniqueness is enforced by the database anyway; catching it here is the
    difference between a form error and a 500."""
    response = world["client"].patch(
        ACCOUNT, {"email": "bob@alpha.test", "current_password": PASSWORD}, format="json"
    )

    assert response.status_code == 400
    assert "email" in response.data
    world["alice"].refresh_from_db()
    assert world["alice"].email == "alice@alpha.test"


def test_keeping_the_same_email_needs_no_password(world):
    """A form that submits every field must not demand a password because the
    unchanged email was included in the payload."""
    response = world["client"].patch(
        ACCOUNT, {"email": "alice@alpha.test", "full_name": "Alice!"}, format="json"
    )
    assert response.status_code == 200


def test_the_endpoint_cannot_edit_another_user(world):
    """There is no id in the URL, so this is really a test that nobody adds one:
    any attempt to name a target must be ignored rather than honoured."""
    world["client"].patch(
        ACCOUNT, {"id": world["bob"].pk, "full_name": "Renamed By Alice"}, format="json"
    )

    world["bob"].refresh_from_db()
    assert world["bob"].full_name == "Bob Brown"


def test_privileged_fields_cannot_be_set_from_this_endpoint(world):
    """`is_staff` grants Django admin. A serializer that accepted unknown fields
    would make self-service profile editing a privilege escalation."""
    world["client"].patch(
        ACCOUNT, {"is_staff": True, "is_active": False, "full_name": "Alice"}, format="json"
    )

    world["alice"].refresh_from_db()
    assert world["alice"].is_staff is False
    assert world["alice"].is_active is True


# ------------------------------------------------------------- passwords ----


def test_changing_a_password_requires_the_current_one(world):
    response = world["client"].post(
        PASSWORD_URL, {"current_password": "wrong", "new_password": "Str0ng!Passphrase42"}
    )

    assert response.status_code == 400
    world["alice"].refresh_from_db()
    assert world["alice"].check_password(PASSWORD)


def test_a_password_changes_with_the_right_current_password(world):
    response = world["client"].post(
        PASSWORD_URL, {"current_password": PASSWORD, "new_password": "Str0ng!Passphrase42"}
    )

    assert response.status_code == 204
    world["alice"].refresh_from_db()
    assert world["alice"].check_password("Str0ng!Passphrase42")


def test_a_weak_password_is_refused(world):
    """Django's validators run here as they do at signup. Skipping them would
    make the settings page the one route to a two-character password."""
    response = world["client"].post(
        PASSWORD_URL, {"current_password": PASSWORD, "new_password": "1234"}
    )

    assert response.status_code == 400
    world["alice"].refresh_from_db()
    assert world["alice"].check_password(PASSWORD)


def test_an_anonymous_request_cannot_change_a_password(world):
    client = APIClient()
    response = client.post(
        PASSWORD_URL,
        {"current_password": PASSWORD, "new_password": "Str0ng!Passphrase42"},
        HTTP_HOST=HOST,
    )
    assert response.status_code in (401, 403)
