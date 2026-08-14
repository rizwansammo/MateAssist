"""The platform tenant registry surface (Phase 7B).

`/platform/tenants/` reads on the RLS-bypassing connection and can suspend a
workspace, so it is tested as a security control first and a feature second. A
tenant admin reaching it would be able to enumerate - and disable - every other
customer on the platform.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.test import APIClient

from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

# `transaction=True` is load-bearing, not incidental.
#
# The `admin` alias is a genuinely separate connection authenticated as the
# superuser (measured: current_user=mateassist, is_superuser=on), which is what
# lets the platform surface read across tenants. Because it is a *different*
# connection, it cannot see the default alias's uncommitted writes - so under a
# normal transactional test every cross-tenant read comes back empty and the
# endpoint looks broken when it is not.
#
# Committing the fixture data costs a slower truncate-based teardown and buys
# tests that exercise the real two-role asymmetry rather than documenting it.
pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "admin"])

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
URL = "/api/v1/platform/tenants/"


def membership(user, tenant, role):
    """Create a membership with RLS armed for the row being written.

    The explicit `transaction.atomic()` is required, not stylistic.
    `set_config('app.tenant_id', ..., true)` is transaction-scoped, and these
    tests run with `transaction=True` - i.e. in autocommit - so without a
    surrounding transaction the arming is discarded the moment the SELECT that
    set it returns, and the policy's WITH CHECK clause refuses the insert.

    This is the same omission that broke `ingest_demo` in Phase 5.
    """
    with transaction.atomic():
        set_db_tenant(tenant.id if tenant else None)
        return Membership.all_objects.create(user=user, tenant=tenant, role=role)


@pytest.fixture
def world():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    owner = User.objects.create_user("owner@platform.test", PASSWORD)
    tenant_admin = User.objects.create_user("admin@alpha.test", PASSWORD)
    member = User.objects.create_user("user@alpha.test", PASSWORD)

    membership(owner, None, Role.PLATFORM_OWNER)
    membership(tenant_admin, alpha, Role.TENANT_ADMIN)
    membership(member, alpha, Role.END_USER)

    return {"alpha": alpha, "beta": beta, "owner": owner, "admin": tenant_admin, "member": member}


def client_for(user, tenant=None):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.slug}.localhost" if tenant else "localhost"
    return client


def rows(response):
    payload = response.data
    return payload if isinstance(payload, list) else payload.get("results", [])


# ------------------------------------------------------------ access ---------


def test_a_workspace_admin_cannot_list_every_tenant(world):
    """The attack this endpoint invites: enumerate the customer base."""
    response = client_for(world["admin"], world["alpha"]).get(URL)
    assert response.status_code == 403


def test_an_end_user_cannot_list_tenants(world):
    assert client_for(world["member"], world["alpha"]).get(URL).status_code == 403


def test_an_anonymous_caller_cannot_list_tenants():
    assert APIClient().get(URL, HTTP_HOST="localhost").status_code in (401, 403)


def test_a_workspace_admin_cannot_suspend_anyone(world):
    """Including themselves - suspension is a platform action, not a tenant one."""
    beta = world["beta"]
    response = client_for(world["admin"], world["alpha"]).post(f"{URL}{beta.id}/suspend/")

    assert response.status_code == 403
    beta.refresh_from_db()
    assert beta.status == Tenant.Status.ACTIVE, "a refused request must not have changed anything"


# ------------------------------------------------------------ behaviour ------


def test_the_owner_sees_every_workspace(world):
    response = client_for(world["owner"]).get(URL)

    assert response.status_code == 200
    assert {row["slug"] for row in rows(response)} == {"alpha", "beta"}


def test_counts_are_annotated_not_zeroed(world):
    """Memberships are tenant-owned and RLS-protected. Annotating them on the
    default connection - where the platform surface has no tenant armed - would
    return zero for every workspace, silently."""
    response = client_for(world["owner"]).get(URL)
    alpha = next(row for row in rows(response) if row["slug"] == "alpha")

    assert alpha["users"] == 2, "two memberships were created for Alpha"
    assert alpha["documents"] == 0


def test_suspend_then_activate_round_trips(world):
    client = client_for(world["owner"])
    alpha = world["alpha"]

    suspended = client.post(f"{URL}{alpha.id}/suspend/")
    assert suspended.status_code == 200
    assert suspended.data["status"] == Tenant.Status.SUSPENDED
    alpha.refresh_from_db()
    assert alpha.status == Tenant.Status.SUSPENDED

    activated = client.post(f"{URL}{alpha.id}/activate/")
    assert activated.status_code == 200
    alpha.refresh_from_db()
    assert alpha.status == Tenant.Status.ACTIVE


def test_suspension_is_audited(world):
    """Cutting off a workspace is an operational event someone will have to
    explain later, so it must leave a record."""
    from apps.audit.models import AuditEvent

    client_for(world["owner"]).post(f"{URL}{world['alpha'].id}/suspend/")

    event = AuditEvent.objects.filter(action="tenant.suspend").order_by("-created_at").first()
    assert event is not None
    assert event.target == "Alpha"
    assert event.metadata.get("slug") == "alpha"


def test_the_registry_is_not_a_delete_surface(world):
    """Deleting a tenant cascades to every row it owns. That is not something an
    HTTP verb should be able to do by accident."""
    response = client_for(world["owner"]).delete(f"{URL}{world['alpha'].id}/")
    assert response.status_code == 405
