"""IsPlatformOwner - the control guarding the credential vault.

This is the only thing standing between a tenant user and every provider key on
the platform, so it gets tested the way Phase 2 tested isolation: by attacking
it, not by confirming the happy path.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ai.models import Engine, ProviderKey
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
ADMIN_HOST = "admin.localhost"
TENANT_HOST = "alpha.localhost"

KEYS_URL = "/api/v1/platform/keys/"


@pytest.fixture
def world():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")

    owner = User.objects.create_user("owner@platform.test", PASSWORD)
    member = User.objects.create_user("user@alpha.test", PASSWORD)
    tenant_admin = User.objects.create_user("admin@alpha.test", PASSWORD)

    set_db_tenant(None)
    Membership.all_objects.create(user=owner, tenant=None, role=Role.PLATFORM_OWNER)
    set_db_tenant(alpha.id)
    Membership.all_objects.create(user=member, tenant=alpha, role=Role.END_USER)
    Membership.all_objects.create(user=tenant_admin, tenant=alpha, role=Role.TENANT_ADMIN)
    set_db_tenant(None)

    return {"alpha": alpha, "owner": owner, "member": member, "tenant_admin": tenant_admin}


def token(email, host):
    response = APIClient().post(
        reverse("accounts:login"),
        {"email": email, "password": PASSWORD},
        format="json",
        HTTP_HOST=host,
    )
    assert response.status_code == 200, response.json()
    return response.json()["access"]


def get_keys(access=None, host=ADMIN_HOST):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {access}"} if access else {}
    return APIClient().get(KEYS_URL, HTTP_HOST=host, **headers)


# ------------------------------------------------------------- rejection ----


def test_anonymous_cannot_reach_the_vault(world):
    assert get_keys().status_code in (401, 403)


def test_tenant_end_user_cannot_reach_the_vault(world):
    """The headline case: a valid session in a workspace must not grant access
    to the platform's provider credentials."""
    access = token("user@alpha.test", TENANT_HOST)
    assert get_keys(access, host=TENANT_HOST).status_code == 403


def test_tenant_admin_cannot_reach_the_vault(world):
    """TENANT_ADMIN is the most privileged tenant role and still must not see
    platform credentials - the roles are per-workspace, not a hierarchy that
    tops out at the platform."""
    access = token("admin@alpha.test", TENANT_HOST)
    assert get_keys(access, host=TENANT_HOST).status_code == 403


def test_tenant_token_replayed_on_the_admin_host_is_refused(world):
    """A validly signed, unexpired tenant token carried to the platform host."""
    access = token("user@alpha.test", TENANT_HOST)
    assert get_keys(access, host=ADMIN_HOST).status_code == 403


def test_platform_owner_is_refused_on_a_tenant_host(world):
    """Even the platform owner cannot operate the vault from inside a workspace.

    The admin bundle is never served on a tenant subdomain (D-145); the
    permission mirrors that at the API so the boundary holds even if someone
    reaches the endpoint directly.
    """
    access = token("owner@platform.test", ADMIN_HOST)
    assert get_keys(access, host=TENANT_HOST).status_code in (403, 404)


def test_revoking_the_membership_revokes_access_immediately(world):
    """Authorisation is re-checked against the database, not read from a token
    claim - so removing someone bites now, not when their token expires."""
    access = token("owner@platform.test", ADMIN_HOST)
    assert get_keys(access).status_code == 200

    # Platform rows (tenant NULL) are reachable on the default connection with
    # no tenant context, which is exactly the RLS predicate doing its job.
    set_db_tenant(None)
    Membership.all_objects.filter(user=world["owner"]).delete()

    assert get_keys(access).status_code == 403


# ----------------------------------------------------------------- allow ----


def test_platform_owner_can_list_keys(world):
    access = token("owner@platform.test", ADMIN_HOST)
    response = get_keys(access)
    assert response.status_code == 200


def test_platform_owner_can_create_a_key_and_gets_no_plaintext_back(world):
    access = token("owner@platform.test", ADMIN_HOST)
    secret = "sk-permission-test-abcdefgh4321"

    response = APIClient().post(
        KEYS_URL,
        {"engine": Engine.TEXT, "label": "perm-test", "secret": secret},
        format="json",
        HTTP_HOST=ADMIN_HOST,
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert response.status_code == 201
    body = response.json()
    assert secret not in str(body), "the vault echoed the plaintext back"
    assert "ciphertext" not in body
    assert body["last4"] == secret[-4:]

    stored = ProviderKey.objects.get(label="perm-test")
    assert secret not in stored.ciphertext
    assert stored.reveal() == secret


def test_mutating_endpoints_are_also_guarded(world):
    """A read-only guard would be worthless: check the write paths too."""
    access = token("user@alpha.test", TENANT_HOST)
    client = APIClient()

    create = client.post(
        KEYS_URL,
        {"engine": Engine.TEXT, "label": "hacked", "secret": "sk-should-never-land"},
        format="json",
        HTTP_HOST=TENANT_HOST,
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert create.status_code == 403
    assert not ProviderKey.objects.filter(label="hacked").exists()
