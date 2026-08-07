"""D-025 - the isolation gate.

This is the test that blocks every later phase. It does not check that the ORM
filters correctly; it checks that the DATABASE refuses, which is the only claim
worth making about multi-tenant isolation.

The strategy is adversarial on purpose: each test tries to reach another
tenant's rows by a different route - the plain manager, the manager that skips
tenant scoping, and finally raw SQL that never touches the ORM at all.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.tenancy.models import Membership, Role, Tenant

pytestmark = pytest.mark.django_db

User = get_user_model()


def set_db_tenant(tenant_id) -> None:
    """Arm RLS exactly as SubdomainMiddleware does."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            ["" if tenant_id is None else str(tenant_id)],
        )


@pytest.fixture
def two_tenants():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    user_a = User.objects.create_user("a@alpha.test", "correct-horse-battery")
    user_b = User.objects.create_user("b@beta.test", "correct-horse-battery")

    # Each membership must be written under its own tenant context: the policy's
    # WITH CHECK clause refuses to insert a row into a tenant you cannot read.
    set_db_tenant(alpha.id)
    Membership.all_objects.create(user=user_a, tenant=alpha, role=Role.END_USER)
    set_db_tenant(beta.id)
    Membership.all_objects.create(user=user_b, tenant=beta, role=Role.END_USER)
    set_db_tenant(None)

    return alpha, beta


# --------------------------------------------------------------- premise ----


def test_connection_role_cannot_bypass_rls():
    """Guards the premise of every other test here.

    PostgreSQL exempts superusers and BYPASSRLS roles from policy. If the
    application ever connects as one, every isolation test below would pass
    while proving nothing at all.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        can_bypass = cursor.fetchone()[0]

    assert (
        can_bypass is False
    ), "the application database role can bypass RLS - isolation is decorative"


def test_policy_is_enabled_and_forced():
    """FORCE matters as much as ENABLE: without it the table owner is exempt,
    and in the test database the app role owns the tables it migrated."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname = 'tenancy_membership'"
        )
        enabled, forced = cursor.fetchone()

    assert enabled is True, "RLS is not enabled on tenancy_membership"
    assert forced is True, "RLS is not FORCEd - the table owner would be exempt"


# ------------------------------------------------------------- isolation ----


def test_orm_sees_only_the_current_tenant(two_tenants):
    alpha, beta = two_tenants

    set_db_tenant(alpha.id)
    from apps.tenancy.context import tenant_context

    with tenant_context(alpha.id):
        rows = list(Membership.objects.all())

    assert len(rows) == 1
    assert rows[0].tenant_id == alpha.id


def test_bypassing_the_tenant_manager_still_cannot_cross_tenants(two_tenants):
    """all_objects deliberately skips TenantScopedManager - the application-layer
    filter. The database must still hold the line on its own."""
    alpha, beta = two_tenants

    set_db_tenant(alpha.id)
    visible = {m.tenant_id for m in Membership.all_objects.all()}

    assert visible == {alpha.id}, f"leaked across tenants: {visible}"


def test_raw_sql_cannot_cross_tenants(two_tenants):
    """THE GATE.

    No ORM, no manager, no queryset - a raw SELECT with no WHERE clause, which
    is exactly what a careless report, a data migration or a hand-written
    analytics query looks like. RLS is the only thing standing here.
    """
    alpha, beta = two_tenants

    set_db_tenant(alpha.id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM tenancy_membership")
        alpha_rows = [row[0] for row in cursor.fetchall()]

    set_db_tenant(beta.id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM tenancy_membership")
        beta_rows = [row[0] for row in cursor.fetchall()]

    assert alpha_rows == [alpha.id], f"raw SQL leaked: {alpha_rows}"
    assert beta_rows == [beta.id], f"raw SQL leaked: {beta_rows}"


def test_explicit_cross_tenant_query_returns_nothing(two_tenants):
    """Even naming the other tenant's id explicitly returns nothing - the
    policy is not merely an implicit filter that a WHERE clause can override."""
    alpha, beta = two_tenants

    set_db_tenant(alpha.id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM tenancy_membership WHERE tenant_id = %s", [beta.id])
        count = cursor.fetchone()[0]

    assert count == 0, "an explicit cross-tenant WHERE clause returned rows"


def test_unset_context_exposes_no_tenant_rows(two_tenants):
    """Fail closed. An unset tenant must mean 'no tenant', never 'all tenants' -
    the difference between a Celery task that does nothing and one that emails
    every workspace's tickets to the wrong customer.
    """
    set_db_tenant(None)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM tenancy_membership WHERE tenant_id IS NOT NULL")
        count = cursor.fetchone()[0]

    assert count == 0, "rows were visible with no tenant context set"


def test_cannot_write_into_another_tenant(two_tenants):
    """WITH CHECK: a row cannot be inserted into a tenant it could not be read
    from. Without it, isolation would be read-only and a bug could still plant
    data in someone else's workspace."""
    alpha, beta = two_tenants
    intruder = User.objects.create_user("intruder@alpha.test", "correct-horse-battery")

    set_db_tenant(alpha.id)
    with pytest.raises(Exception) as exc:
        Membership.all_objects.create(user=intruder, tenant=beta, role=Role.END_USER)

    assert "policy" in str(exc.value).lower() or "violates" in str(exc.value).lower()


def test_platform_rows_are_invisible_from_inside_a_tenant(two_tenants):
    """PLATFORM_OWNER memberships carry a null tenant. A workspace must not be
    able to enumerate platform staff."""
    alpha, _ = two_tenants
    owner = User.objects.create_user("owner@platform.test", "correct-horse-battery")

    set_db_tenant(None)
    Membership.all_objects.create(user=owner, tenant=None, role=Role.PLATFORM_OWNER)

    set_db_tenant(alpha.id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM tenancy_membership WHERE tenant_id IS NULL")
        count = cursor.fetchone()[0]

    assert count == 0, "platform-level rows were visible from inside a tenant"
