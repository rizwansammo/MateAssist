"""RLS for knowledge tables (D-020).

The most sensitive data in the product: a workspace's runbooks and the vectors
derived from them. A retrieval query that crossed tenants would put one
customer's internal procedures into another customer's chat answer.

knowledge_documentasset carries no tenant_id of its own - it is reachable only
through its Document - so it is protected by an EXISTS check against the parent
rather than a direct comparison.
"""

from django.db import migrations

PREDICATE = """(
  CASE
    WHEN app_current_tenant_id() IS NULL THEN tenant_id IS NULL
    ELSE tenant_id = app_current_tenant_id()
  END
)"""

ASSET_PREDICATE = """(
  EXISTS (
    SELECT 1 FROM knowledge_document d
    WHERE d.id = knowledge_documentasset.document_id
      AND d.tenant_id = app_current_tenant_id()
  )
)"""


def _policy(table: str, predicate: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
  USING {predicate}
  WITH CHECK {predicate};
"""


def _drop(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0001_initial"),
        ("tenancy", "0002_rls_policies"),  # provides app_current_tenant_id()
    ]

    operations = [
        migrations.RunSQL(_policy("knowledge_category", PREDICATE), _drop("knowledge_category")),
        migrations.RunSQL(_policy("knowledge_document", PREDICATE), _drop("knowledge_document")),
        migrations.RunSQL(
            _policy("knowledge_documentchunk", PREDICATE), _drop("knowledge_documentchunk")
        ),
        migrations.RunSQL(
            _policy("knowledge_documentasset", ASSET_PREDICATE),
            _drop("knowledge_documentasset"),
        ),
    ]
