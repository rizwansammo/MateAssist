"""RLS for audit events (D-020, D-114).

A tenant may read its own event stream; platform-level events (tenant_id NULL)
are visible only with no tenant context, i.e. on the platform-admin surface.
Identical predicate to every other tenant-owned table.
"""

from django.db import migrations

PREDICATE = """(
  CASE
    WHEN app_current_tenant_id() IS NULL THEN tenant_id IS NULL
    ELSE tenant_id = app_current_tenant_id()
  END
)"""

ENABLE = f"""
ALTER TABLE audit_auditevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_auditevent FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON audit_auditevent;
CREATE POLICY tenant_isolation ON audit_auditevent
  USING {PREDICATE}
  WITH CHECK {PREDICATE};
"""

DISABLE = """
DROP POLICY IF EXISTS tenant_isolation ON audit_auditevent;
ALTER TABLE audit_auditevent NO FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_auditevent DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
        ("tenancy", "0002_rls_policies"),
    ]

    operations = [migrations.RunSQL(ENABLE, DISABLE)]
