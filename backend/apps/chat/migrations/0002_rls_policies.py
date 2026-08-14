"""RLS for chat tables (D-020).

Conversations carry what people typed into a support tool - error messages,
system names, sometimes credentials they should not have pasted. A cross-tenant
read here is the worst leak in the product.
"""

from django.db import migrations

PREDICATE = """(
  CASE
    WHEN app_current_tenant_id() IS NULL THEN tenant_id IS NULL
    ELSE tenant_id = app_current_tenant_id()
  END
)"""


def _policy(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
  USING {PREDICATE}
  WITH CHECK {PREDICATE};
"""


def _drop(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0001_initial"),
        ("tenancy", "0002_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(_policy("chat_conversation"), _drop("chat_conversation")),
        migrations.RunSQL(_policy("chat_message"), _drop("chat_message")),
        migrations.RunSQL(_policy("chat_messagefeedback"), _drop("chat_messagefeedback")),
    ]
