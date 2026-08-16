"""Creating workspaces and people through the product (D-173).

Every account used to come from a management command over SSH, so onboarding a
customer or a single new hire required server access. These are the two paths
that replace it, and they are the paths that mint credentials - so most of what
follows is about who cannot use them, and about not leaving half-made accounts
behind when something fails.
"""

from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.test import APIClient

from apps.tenancy import provisioning
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

# Both connections, committed for real. The platform endpoints read through the
# RLS-bypassing `admin` alias, which is a genuinely separate session and cannot
# see rows an uncommitted test transaction holds - the same wall Phase 7A hit.
pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "admin"])

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
STRONG = "Str0ng!Passphrase42"

TENANTS_URL = "/api/v1/platform/tenants/"
USERS_URL = "/api/v1/workspace/users/"


@pytest.fixture
def owner():
    set_db_tenant(None)
    user = User.objects.create_user("owner@platform.test", PASSWORD)
    Membership.all_objects.create(user=user, tenant=None, role=Role.PLATFORM_OWNER)
    return user


@pytest.fixture
def workspace():
    tenant = Tenant.objects.create(name="Alpha", slug="alpha")
    admin = User.objects.create_user("admin@alpha.test", PASSWORD)
    member = User.objects.create_user("user@alpha.test", PASSWORD)

    # The arming and the INSERTs must share a transaction: set_config is
    # transaction-scoped and every statement autocommits under transaction=True,
    # so otherwise the RLS WITH CHECK clause refuses the rows.
    with transaction.atomic():
        set_db_tenant(tenant.id)
        Membership.all_objects.create(user=admin, tenant=tenant, role=Role.TENANT_ADMIN)
        Membership.all_objects.create(user=member, tenant=tenant, role=Role.END_USER)

    tenant.owner = admin
    tenant.save(update_fields=["owner"])
    return {"tenant": tenant, "admin": admin, "member": member}


@contextmanager
def armed(tenant):
    """Read tenant-owned rows in a test.

    Both halves are required. `set_config(..., true)` is transaction-scoped and
    every statement autocommits under transaction=True, so arming outside a
    transaction is discarded before the SELECT runs - and RLS then returns an
    empty result that reads exactly like a write that never happened.
    """
    with transaction.atomic():
        set_db_tenant(getattr(tenant, "pk", tenant))
        yield


def client_for(user, host="alpha.localhost"):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = host
    return client


# ------------------------------------------------- creating a workspace -----


def test_a_platform_owner_creates_a_workspace_and_its_admin(owner):
    """The whole point: a second customer without touching the server."""
    response = client_for(owner, host="admin.localhost").post(
        TENANTS_URL,
        {"name": "Beta Industries", "admin_email": "it@beta.test", "admin_name": "Beta Admin"},
        format="json",
    )

    assert response.status_code == 201, response.data
    tenant = Tenant.objects.get(name="Beta Industries")
    assert tenant.slug == "beta-industries"
    assert tenant.owner.email == "it@beta.test"

    with armed(tenant):
        assert Membership.all_objects.filter(
            tenant=tenant, user=tenant.owner, role=Role.TENANT_ADMIN
        ).exists()


def test_the_admin_password_is_returned_once_and_works(owner):
    response = client_for(owner, host="admin.localhost").post(
        TENANTS_URL, {"name": "Gamma", "admin_email": "it@gamma.test"}, format="json"
    )

    password = response.data["owner_password"]
    assert len(password) >= 12
    # Dictated down a phone line, these are the characters people get wrong.
    assert not set("O0lI1") & set(password)
    assert User.objects.get(email="it@gamma.test").check_password(password)


def test_a_chosen_password_is_used_as_given(owner):
    client_for(owner, host="admin.localhost").post(
        TENANTS_URL,
        {"name": "Delta", "admin_email": "it@delta.test", "admin_password": STRONG},
        format="json",
    )

    assert User.objects.get(email="it@delta.test").check_password(STRONG)


def test_a_weak_chosen_password_creates_nothing(owner):
    """The failure that must not leave debris: a workspace with no
    administrator cannot be signed into and appears in nobody's list."""
    response = client_for(owner, host="admin.localhost").post(
        TENANTS_URL,
        {"name": "Weak Co", "admin_email": "it@weak.test", "admin_password": "1234"},
        format="json",
    )

    assert response.status_code == 400
    assert not Tenant.objects.filter(name="Weak Co").exists()
    assert not User.objects.filter(email="it@weak.test").exists()


def test_a_duplicate_admin_email_creates_nothing(owner, workspace):
    response = client_for(owner, host="admin.localhost").post(
        TENANTS_URL,
        {"name": "Clash Co", "admin_email": "admin@alpha.test"},
        format="json",
    )

    assert response.status_code == 400
    assert not Tenant.objects.filter(name="Clash Co").exists()


def test_slugs_are_derived_and_never_collide(owner):
    """`slug` was read-only with nothing deriving it, so the first workspace
    created through the API had an empty subdomain and the second 500ed on the
    unique index."""
    client = client_for(owner, host="admin.localhost")
    client.post(TENANTS_URL, {"name": "Acme", "admin_email": "a@one.test"}, format="json")
    client.post(TENANTS_URL, {"name": "Acme", "admin_email": "a@two.test"}, format="json")

    slugs = sorted(Tenant.objects.filter(name="Acme").values_list("slug", flat=True))
    assert slugs == ["acme", "acme-2"]


def test_a_reserved_subdomain_is_not_handed_out(owner):
    """`admin.mateassist.site` is the console. A workspace there would shadow
    it, and one at `api` or `www` would be unreachable."""
    client_for(owner, host="admin.localhost").post(
        TENANTS_URL, {"name": "Admin", "admin_email": "it@admin.test"}, format="json"
    )

    assert Tenant.objects.get(name="Admin").slug != "admin"


def test_a_tenant_admin_cannot_create_a_workspace(workspace):
    """Creating workspaces is platform business. A customer must not be able to
    mint another one."""
    response = client_for(workspace["admin"]).post(
        TENANTS_URL, {"name": "Sneaky", "admin_email": "x@sneaky.test"}, format="json"
    )

    assert response.status_code == 403
    assert not Tenant.objects.filter(name="Sneaky").exists()


# --------------------------------------------------- creating a member ------


def test_an_admin_adds_someone_to_their_workspace(workspace):
    response = client_for(workspace["admin"]).post(
        USERS_URL, {"email": "new@alpha.test", "full_name": "New Person"}, format="json"
    )

    assert response.status_code == 201
    user = User.objects.get(email="new@alpha.test")
    assert user.check_password(response.data["password"])

    with armed(workspace["tenant"]):
        assert Membership.all_objects.filter(
            user=user, tenant=workspace["tenant"], role=Role.END_USER
        ).exists()


def test_a_new_member_lands_in_this_workspace_only(workspace):
    """`tenant` is taken from the request, so naming another workspace is not
    refused - it cannot be expressed."""
    other = Tenant.objects.create(name="Beta", slug="beta")

    client_for(workspace["admin"]).post(
        USERS_URL, {"email": "new@alpha.test", "tenant": other.pk}, format="json"
    )

    user = User.objects.get(email="new@alpha.test")

    with armed(other):
        assert not Membership.all_objects.filter(user=user, tenant=other).exists()
    with armed(workspace["tenant"]):
        assert Membership.all_objects.filter(user=user, tenant=workspace["tenant"]).exists()


def test_an_email_already_in_use_is_refused_without_creating_anything(workspace):
    response = client_for(workspace["admin"]).post(
        USERS_URL, {"email": "user@alpha.test"}, format="json"
    )

    assert response.status_code == 400
    with armed(workspace["tenant"]):
        assert Membership.all_objects.filter(tenant=workspace["tenant"]).count() == 2


def test_an_end_user_cannot_add_anyone(workspace):
    response = client_for(workspace["member"]).post(
        USERS_URL, {"email": "smuggled@alpha.test"}, format="json"
    )

    assert response.status_code == 403
    assert not User.objects.filter(email="smuggled@alpha.test").exists()


def test_an_admin_can_promote_a_new_person_to_administrator(workspace):
    client_for(workspace["admin"]).post(
        USERS_URL, {"email": "second@alpha.test", "role": Role.TENANT_ADMIN}, format="json"
    )

    with armed(workspace["tenant"]):
        membership = Membership.all_objects.get(user__email="second@alpha.test")
        assert membership.role == Role.TENANT_ADMIN


def test_platform_owner_is_not_an_assignable_role(workspace):
    """Otherwise a tenant admin could mint themselves a colleague with the keys
    to every workspace."""
    response = client_for(workspace["admin"]).post(
        USERS_URL, {"email": "sneaky@alpha.test", "role": Role.PLATFORM_OWNER}, format="json"
    )

    assert response.status_code == 400
    assert not User.objects.filter(email="sneaky@alpha.test").exists()


# ------------------------------------------------------- deactivating -------


def access_url(user):
    return f"/api/v1/workspace/users/{user.pk}/access/"


def test_an_admin_can_deactivate_a_member(workspace):
    """A leaver keeps working access otherwise - the gap that made "create
    users" only half a lifecycle."""
    response = client_for(workspace["admin"]).patch(
        access_url(workspace["member"]), {"is_active": False}, format="json"
    )

    assert response.status_code == 200
    workspace["member"].refresh_from_db()
    assert workspace["member"].is_active is False


def test_a_deactivated_member_cannot_sign_in(workspace):
    from django.urls import reverse

    workspace["member"].is_active = False
    workspace["member"].save(update_fields=["is_active"])

    response = APIClient().post(
        reverse("accounts:login"),
        {"email": "user@alpha.test", "password": PASSWORD},
        format="json",
        HTTP_HOST="alpha.localhost",
    )
    assert response.status_code != 200


def test_deactivation_is_reversible(workspace):
    """Deactivating rather than deleting is the whole point: the person's
    conversations are the workspace's record of what its desk was asked."""
    client = client_for(workspace["admin"])
    client.patch(access_url(workspace["member"]), {"is_active": False}, format="json")
    client.patch(access_url(workspace["member"]), {"is_active": True}, format="json")

    workspace["member"].refresh_from_db()
    assert workspace["member"].is_active is True


def test_an_admin_cannot_deactivate_themselves(workspace):
    """They would be locked out of the screen that undoes it."""
    response = client_for(workspace["admin"]).patch(
        access_url(workspace["admin"]), {"is_active": False}, format="json"
    )

    assert response.status_code == 400
    workspace["admin"].refresh_from_db()
    assert workspace["admin"].is_active is True


def test_a_tenant_admin_cannot_deactivate_a_platform_owner(workspace, owner):
    """One shared User row: disabling it would lock the platform owner out of
    the console from a screen scoped to one workspace (D-159)."""
    with transaction.atomic():
        set_db_tenant(workspace["tenant"].id)
        Membership.all_objects.create(user=owner, tenant=workspace["tenant"], role=Role.END_USER)

    response = client_for(workspace["admin"]).patch(
        access_url(owner), {"is_active": False}, format="json"
    )

    assert response.status_code == 403
    owner.refresh_from_db()
    assert owner.is_active is True


def test_an_admin_cannot_deactivate_someone_in_another_workspace(workspace):
    other = Tenant.objects.create(name="Beta", slug="beta")
    outsider = User.objects.create_user("user@beta.test", PASSWORD)
    with transaction.atomic():
        set_db_tenant(other.id)
        Membership.all_objects.create(user=outsider, tenant=other, role=Role.END_USER)

    response = client_for(workspace["admin"]).patch(
        access_url(outsider), {"is_active": False}, format="json"
    )

    assert response.status_code == 404
    outsider.refresh_from_db()
    assert outsider.is_active is True


def test_an_end_user_cannot_deactivate_anyone(workspace):
    response = client_for(workspace["member"]).patch(
        access_url(workspace["admin"]), {"is_active": False}, format="json"
    )

    assert response.status_code == 403
    workspace["admin"].refresh_from_db()
    assert workspace["admin"].is_active is True


# --------------------------------------------- resetting the owner ----------


def test_the_platform_owner_can_reset_a_workspace_owners_password(owner, workspace):
    response = client_for(owner, host="admin.localhost").post(
        f"{TENANTS_URL}{workspace['tenant'].pk}/reset-owner-password/", {}, format="json"
    )

    assert response.status_code == 200
    workspace["admin"].refresh_from_db()
    assert workspace["admin"].check_password(response.data["password"])


def test_a_tenant_admin_cannot_reset_another_workspaces_owner(workspace):
    response = client_for(workspace["admin"]).post(
        f"{TENANTS_URL}{workspace['tenant'].pk}/reset-owner-password/", {}, format="json"
    )
    assert response.status_code == 403


# ------------------------------------------------------------- helpers ------


def test_generated_passwords_are_not_predictable():
    """`secrets`, not `random`: this mints credentials."""
    passwords = {provisioning.generate_password() for _ in range(200)}
    assert len(passwords) == 200
