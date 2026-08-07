"""Row Level Security policies (D-020).

This is the isolation guarantee. Everything in Python - managers, middleware,
serializers - is convenience on top of it. A raw query, a forgotten filter or a
Celery task that never set a tenant still cannot read another workspace's rows,
because the database refuses.

Design notes:

* FORCE ROW LEVEL SECURITY is set as well as ENABLE. Without FORCE, the table
  OWNER is exempt - and in the pytest test database the application role owns
  the tables it migrates, so policies would silently not apply there. The test
  suite would then prove nothing, which is the failure mode this phase exists
  to prevent.

* Unset tenant context means "no tenant", never "all tenants". With no
  app.tenant_id the policy admits only platform-level rows (tenant_id IS NULL),
  which is what lets a PLATFORM_OWNER authenticate on the admin host while
  remaining unable to read any workspace's data.

* tenancy_tenant is deliberately NOT policy-protected: it is the registry of
  workspaces, not data belonging to one. Tenant-owned tables added in later
  phases inherit from TenantScopedModel and get the same treatment as
  tenancy_membership.
"""

from django.db import migrations

TENANT_FN = """
CREATE OR REPLACE FUNCTION app_current_tenant_id() RETURNS bigint
LANGUAGE sql STABLE AS $fn$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::bigint
$fn$;
"""

DROP_TENANT_FN = "DROP FUNCTION IF EXISTS app_current_tenant_id();"

# One predicate, used for both reads (USING) and writes (WITH CHECK), so a row
# can never be inserted or updated into a tenant it could not be read from.
PREDICATE = """(
  CASE
    WHEN app_current_tenant_id() IS NULL THEN tenant_id IS NULL
    ELSE tenant_id = app_current_tenant_id()
  END
)"""

ENABLE_MEMBERSHIP_RLS = f"""
ALTER TABLE tenancy_membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy_membership FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON tenancy_membership;
CREATE POLICY tenant_isolation ON tenancy_membership
  USING {PREDICATE}
  WITH CHECK {PREDICATE};
"""

DISABLE_MEMBERSHIP_RLS = """
DROP POLICY IF EXISTS tenant_isolation ON tenancy_membership;
ALTER TABLE tenancy_membership NO FORCE ROW LEVEL SECURITY;
ALTER TABLE tenancy_membership DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0001_initial")]

    operations = [
        migrations.RunSQL(TENANT_FN, DROP_TENANT_FN),
        migrations.RunSQL(ENABLE_MEMBERSHIP_RLS, DISABLE_MEMBERSHIP_RLS),
    ]
