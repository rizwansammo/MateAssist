"""RLS for usage events (D-020).

Spend and volume are commercially sensitive: one workspace must not be able to
infer another's. Same predicate as tenancy_membership, so every tenant-owned
table in the system is protected identically.
"""

from django.db import migrations

PREDICATE = """(
  CASE
    WHEN app_current_tenant_id() IS NULL THEN tenant_id IS NULL
    ELSE tenant_id = app_current_tenant_id()
  END
)"""

ENABLE = f"""
ALTER TABLE metering_usageevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE metering_usageevent FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON metering_usageevent;
CREATE POLICY tenant_isolation ON metering_usageevent
  USING {PREDICATE}
  WITH CHECK {PREDICATE};
"""

DISABLE = """
DROP POLICY IF EXISTS tenant_isolation ON metering_usageevent;
ALTER TABLE metering_usageevent NO FORCE ROW LEVEL SECURITY;
ALTER TABLE metering_usageevent DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("metering", "0001_initial"),
        ("tenancy", "0002_rls_policies"),  # provides app_current_tenant_id()
    ]

    operations = [migrations.RunSQL(ENABLE, DISABLE)]
