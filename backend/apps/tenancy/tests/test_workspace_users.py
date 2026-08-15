"""Workspace user management (D-159).

A tenant administrator can see everyone in their workspace and reset any of
their passwords. That is a real power, so most of this file is about its edges:
the workspace next door, and the platform owner.

The escalation these tests exist for: a User is global and one row may hold both
a TENANT_ADMIN membership in a workspace and PLATFORM_OWNER at the platform.
Resetting "a member's" password would then hand a tenant admin the platform
console - every workspace's data and the credential vault - from a screen that
is scoped to one workspace.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"

USERS_URL = "/api/v1/workspace/users/"


def reset_url(user):
    return f"/api/v1/workspace/users/{user.pk}/reset-password/"


@pytest.fixture
def world():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    admin = User.objects.create_user("admin@alpha.test", PASSWORD, full_name="Alpha Admin")
    second_admin = User.objects.create_user("admin2@alpha.test", PASSWORD)
    member = User.objects.create_user("user@alpha.test", PASSWORD, full_name="Alpha User")
    outsider = User.objects.create_user("user@beta.test", PASSWORD)
    owner = User.objects.create_user("owner@platform.test", PASSWORD)

    set_db_tenant(alpha.id)
    Membership.all_objects.create(user=admin, tenant=alpha, role=Role.TENANT_ADMIN)
    Membership.all_objects.create(user=second_admin, tenant=alpha, role=Role.TENANT_ADMIN)
    Membership.all_objects.create(user=member, tenant=alpha, role=Role.END_USER)
    # The dangerous shape: the platform owner also sits in this workspace.
    Membership.all_objects.create(user=owner, tenant=alpha, role=Role.END_USER)

    set_db_tenant(beta.id)
    Membership.all_objects.create(user=outsider, tenant=beta, role=Role.END_USER)

    set_db_tenant(None)
    Membership.all_objects.create(user=owner, tenant=None, role=Role.PLATFORM_OWNER)

    return {
        "alpha": alpha,
        "admin": admin,
        "second_admin": second_admin,
        "member": member,
        "outsider": outsider,
        "owner": owner,
    }


def client_for(user, host="alpha.localhost"):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = host
    return client


# ------------------------------------------------------------------ listing --


def test_an_admin_sees_everyone_in_their_workspace(world):
    response = client_for(world["admin"]).get(USERS_URL)

    assert response.status_code == 200
    emails = {row["email"] for row in response.data}
    assert emails == {
        "admin@alpha.test",
        "admin2@alpha.test",
        "user@alpha.test",
        "owner@platform.test",
    }


def test_the_list_never_includes_another_workspace(world):
    """Memberships are listed, not users. Listing users directly would
    enumerate every person on the platform to every tenant admin."""
    response = client_for(world["admin"]).get(USERS_URL)
    assert "user@beta.test" not in {row["email"] for row in response.data}


def test_the_list_carries_no_password_material(world):
    body = str(client_for(world["admin"]).get(USERS_URL).data)
    assert "password" not in body.lower()
    assert "pbkdf2" not in body.lower()


def test_an_end_user_cannot_list_the_workspace(world):
    """An end user has no reason to enumerate their colleagues, and the list is
    the reconnaissance step before anything else here."""
    assert client_for(world["member"]).get(USERS_URL).status_code == 403


def test_an_admin_of_another_workspace_cannot_list_this_one(world):
    response = client_for(world["outsider"], host="beta.localhost").get(USERS_URL)
    assert response.status_code == 403


# ---------------------------------------------------------------- resetting --


def test_an_admin_can_reset_a_members_password(world):
    response = client_for(world["admin"]).post(reset_url(world["member"]), {}, format="json")

    assert response.status_code == 200
    world["member"].refresh_from_db()
    assert world["member"].check_password(response.data["password"])
    assert not world["member"].check_password(PASSWORD)


def test_a_generated_password_is_returned_once_and_is_not_trivial(world):
    response = client_for(world["admin"]).post(reset_url(world["member"]), {}, format="json")

    password = response.data["password"]
    assert len(password) >= 12
    # Dictated down a phone line, these are the characters people get wrong.
    assert not set("O0lI1") & set(password)


def test_an_admin_can_set_a_specific_password(world):
    client_for(world["admin"]).post(
        reset_url(world["member"]), {"new_password": "Str0ng!Passphrase42"}, format="json"
    )

    world["member"].refresh_from_db()
    assert world["member"].check_password("Str0ng!Passphrase42")


def test_a_weak_chosen_password_is_refused(world):
    response = client_for(world["admin"]).post(
        reset_url(world["member"]), {"new_password": "1234"}, format="json"
    )

    assert response.status_code == 400
    world["member"].refresh_from_db()
    assert world["member"].check_password(PASSWORD)


def test_an_admin_can_reset_another_admin(world):
    """Asked for explicitly: an administrator locked out of their own workspace
    should not need the platform owner to get back in."""
    response = client_for(world["admin"]).post(reset_url(world["second_admin"]), {}, format="json")

    assert response.status_code == 200
    world["second_admin"].refresh_from_db()
    assert world["second_admin"].check_password(response.data["password"])


# ---------------------------------------------------------------- refusals ---


def test_a_platform_owner_cannot_be_reset_by_a_tenant_admin(world):
    """The privilege escalation this endpoint could have been.

    The owner holds an END_USER membership in Alpha, so they are a legitimate
    member of this workspace - but the password is on the shared User row, and
    setting it would give a tenant admin the platform console.
    """
    response = client_for(world["admin"]).post(reset_url(world["owner"]), {}, format="json")

    assert response.status_code == 403
    world["owner"].refresh_from_db()
    assert world["owner"].check_password(PASSWORD)


def test_a_user_from_another_workspace_cannot_be_reset(world):
    """The id resolves to a real user, just not one of theirs. It must fail on
    the membership lookup rather than on a check someone remembered to add."""
    response = client_for(world["admin"]).post(reset_url(world["outsider"]), {}, format="json")

    assert response.status_code == 404
    world["outsider"].refresh_from_db()
    assert world["outsider"].check_password(PASSWORD)


def test_an_end_user_cannot_reset_anyone(world):
    response = client_for(world["member"]).post(reset_url(world["admin"]), {}, format="json")

    assert response.status_code == 403
    world["admin"].refresh_from_db()
    assert world["admin"].check_password(PASSWORD)


def test_an_anonymous_request_cannot_reset_anyone(world):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "alpha.localhost"
    response = client.post(reset_url(world["member"]), {}, format="json")

    assert response.status_code in (401, 403)
    world["member"].refresh_from_db()
    assert world["member"].check_password(PASSWORD)
