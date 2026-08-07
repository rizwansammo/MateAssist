"""Authentication and tenant-scoped login (D-030..D-036).

Requests carry an explicit HTTP_HOST rather than relying on DNS: *.localhost
does not resolve outside a browser (A-007), and the middleware reads the Host
header anyway, so this exercises the real production path.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def world():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    alice = User.objects.create_user("alice@alpha.test", PASSWORD, full_name="Alice Alpha")
    bob = User.objects.create_user("bob@beta.test", PASSWORD, full_name="Bob Beta")

    set_db_tenant(alpha.id)
    Membership.all_objects.create(user=alice, tenant=alpha, role=Role.TENANT_ADMIN)
    set_db_tenant(beta.id)
    Membership.all_objects.create(user=bob, tenant=beta, role=Role.END_USER)
    set_db_tenant(None)

    return {"alpha": alpha, "beta": beta, "alice": alice, "bob": bob}


def login(client, email, host, password=PASSWORD):
    return client.post(
        reverse("accounts:login"),
        {"email": email, "password": password},
        format="json",
        HTTP_HOST=host,
    )


def test_login_succeeds_on_the_users_own_workspace(world):
    response = login(APIClient(), "alice@alpha.test", "alpha.localhost")

    assert response.status_code == 200
    body = response.json()
    assert body["access"]
    assert body["role"] == Role.TENANT_ADMIN
    assert body["tenant"]["slug"] == "alpha"
    assert body["user"]["email"] == "alice@alpha.test"


def test_refresh_token_is_httponly_and_never_in_the_body(world):
    """D-032: the refresh token must be unreachable from JavaScript, so it goes
    in an httpOnly cookie scoped to the auth path and never into the payload."""
    client = APIClient()
    response = login(client, "alice@alpha.test", "alpha.localhost")

    assert "refresh" not in response.json(), "refresh token leaked into the response body"

    cookie = response.cookies.get("mateassist_refresh")
    assert cookie is not None, "no refresh cookie was set"
    assert cookie["httponly"], "refresh cookie is readable by JavaScript"
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["samesite"] == "Lax"


def test_valid_credentials_are_rejected_on_another_tenants_subdomain(world):
    """D-034: credentials are validated against the tenant in the Host header.

    Bob's password is correct - he simply is not a member of Alpha. This is the
    single most important auth test in the phase: without it, any user of any
    workspace could sign in to every other workspace.
    """
    response = login(APIClient(), "bob@beta.test", "alpha.localhost")

    assert response.status_code == 400
    assert "Invalid credentials" in str(response.json())


def test_failure_modes_are_indistinguishable(world):
    """Wrong password, unknown user and not-a-member must look identical, or the
    login form becomes an oracle for enumerating a workspace's staff."""
    wrong_password = login(APIClient(), "alice@alpha.test", "alpha.localhost", "wrong")
    unknown_user = login(APIClient(), "nobody@alpha.test", "alpha.localhost")
    not_a_member = login(APIClient(), "bob@beta.test", "alpha.localhost")

    bodies = {str(r.json()) for r in (wrong_password, unknown_user, not_a_member)}
    statuses = {r.status_code for r in (wrong_password, unknown_user, not_a_member)}

    assert len(bodies) == 1, f"responses differ and leak account state: {bodies}"
    assert statuses == {400}


def test_suspended_workspace_blocks_sign_in(world):
    """D-035: suspension takes effect immediately, before credentials matter."""
    alpha = world["alpha"]
    alpha.status = Tenant.Status.SUSPENDED
    alpha.save()

    response = login(APIClient(), "alice@alpha.test", "alpha.localhost")

    assert response.status_code == 403
    assert "suspended" in str(response.json()).lower()


def test_unknown_workspace_is_rejected(world):
    response = login(APIClient(), "alice@alpha.test", "nosuchtenant.localhost")
    assert response.status_code == 404


def test_refresh_rotates_and_blacklists_the_old_token(world):
    """A stolen refresh token must be usable at most once."""
    client = APIClient()
    login(client, "alice@alpha.test", "alpha.localhost")
    original = client.cookies["mateassist_refresh"].value

    first = client.post(reverse("accounts:refresh"), HTTP_HOST="alpha.localhost")
    assert first.status_code == 200
    assert client.cookies["mateassist_refresh"].value != original, "token was not rotated"

    # Replay the original, now-blacklisted token.
    replay = APIClient()
    replay.cookies["mateassist_refresh"] = original
    assert replay.post(reverse("accounts:refresh"), HTTP_HOST="alpha.localhost").status_code == 401


def test_refresh_rechecks_membership(world):
    """Revoking access must bite within the access-token lifetime, not at next
    login - otherwise a removed employee keeps working for a week."""
    client = APIClient()
    login(client, "alice@alpha.test", "alpha.localhost")

    set_db_tenant(world["alpha"].id)
    Membership.all_objects.filter(user=world["alice"]).delete()
    set_db_tenant(None)

    assert client.post(reverse("accounts:refresh"), HTTP_HOST="alpha.localhost").status_code == 401


def test_logout_clears_and_blacklists(world):
    client = APIClient()
    login(client, "alice@alpha.test", "alpha.localhost")
    token = client.cookies["mateassist_refresh"].value

    assert client.post(reverse("accounts:logout"), HTTP_HOST="alpha.localhost").status_code == 204

    replay = APIClient()
    replay.cookies["mateassist_refresh"] = token
    assert replay.post(reverse("accounts:refresh"), HTTP_HOST="alpha.localhost").status_code == 401


def test_me_requires_authentication(world):
    assert APIClient().get(reverse("accounts:me"), HTTP_HOST="alpha.localhost").status_code == 401


def test_me_returns_the_session_for_the_current_workspace(world):
    client = APIClient()
    access = login(client, "alice@alpha.test", "alpha.localhost").json()["access"]

    response = client.get(
        reverse("accounts:me"),
        HTTP_HOST="alpha.localhost",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert response.status_code == 200
    assert response.json()["tenant"]["slug"] == "alpha"
    assert response.json()["role"] == Role.TENANT_ADMIN


def test_access_token_from_one_tenant_is_useless_on_another(world):
    """The tenant is re-resolved from the Host header on every request, so a
    token minted for Alpha grants nothing on Beta even though it is validly
    signed and unexpired."""
    client = APIClient()
    access = login(client, "alice@alpha.test", "alpha.localhost").json()["access"]

    response = APIClient().get(
        reverse("accounts:me"),
        HTTP_HOST="beta.localhost",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert response.status_code == 403
