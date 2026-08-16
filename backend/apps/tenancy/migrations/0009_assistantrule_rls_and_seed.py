"""RLS for assistant rules, and the split of the old textarea (D-167).

Two things that must happen together: the new table has to be protected like
every other tenant-owned table, and the text people have already written has to
survive the change. A migration that added the table and left the existing
instructions behind would silently empty a page a customer had already filled
in.
"""

from django.db import migrations

PREDICATE = """(
  CASE
    WHEN app_current_tenant_id() IS NULL THEN tenant_id IS NULL
    ELSE tenant_id = app_current_tenant_id()
  END
)"""

ENABLE_RLS = f"""
ALTER TABLE tenancy_assistantrule ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy_assistantrule FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON tenancy_assistantrule;
CREATE POLICY tenant_isolation ON tenancy_assistantrule
  USING {PREDICATE}
  WITH CHECK {PREDICATE};
"""

DISABLE_RLS = """
DROP POLICY IF EXISTS tenant_isolation ON tenancy_assistantrule;
ALTER TABLE tenancy_assistantrule NO FORCE ROW LEVEL SECURITY;
ALTER TABLE tenancy_assistantrule DISABLE ROW LEVEL SECURITY;
"""


def split_existing_instructions(apps, schema_editor):
    """Turn each workspace's textarea into rules, split on blank lines.

    Blank lines rather than newlines: people already write these as paragraphs,
    and splitting every line would turn a two-line rule into two half-rules that
    each read as nonsense.

    EVERY query here must name `schema_editor.connection.alias`.

    Migrations run on the `admin` alias, because the default connection is the
    under-privileged RLS role and cannot alter tables. A bare `.objects` query
    inside RunPython uses the DEFAULT connection instead - a second, separate
    session. This migration takes an ACCESS EXCLUSIVE lock on the table in the
    admin transaction, so a default-connection INSERT then waits for a lock its
    own migration is holding, and waits forever.

    That is exactly what happened in production: the ALTER sat idle in
    transaction for over an hour while the INSERT queued behind it, the deploy
    appeared to be an SSH failure, and the table was left with no RLS policy.
    """
    database = schema_editor.connection.alias
    Tenant = apps.get_model("tenancy", "Tenant")
    AssistantRule = apps.get_model("tenancy", "AssistantRule")

    for tenant in Tenant.objects.using(database).exclude(assistant_instructions="").iterator():
        chunks = [
            chunk.strip()
            for chunk in tenant.assistant_instructions.replace("\r\n", "\n").split("\n\n")
        ]
        rules = [chunk for chunk in chunks if chunk]

        AssistantRule.objects.using(database).bulk_create(
            [
                AssistantRule(tenant=tenant, text=text[:500], enabled=True, position=index)
                for index, text in enumerate(rules)
            ]
        )


def rejoin_into_instructions(apps, schema_editor):
    """Reverse: fold the rules back into the textarea.

    Without this the migration is one-way, and a rollback would leave a
    workspace with no instructions at all rather than the ones it started with.

    Same connection rule as the forward direction: a rollback also drops the RLS
    policy under an exclusive lock, so reading on the default connection would
    deadlock against it in exactly the same way.
    """
    database = schema_editor.connection.alias
    Tenant = apps.get_model("tenancy", "Tenant")
    AssistantRule = apps.get_model("tenancy", "AssistantRule")

    for tenant in Tenant.objects.using(database).iterator():
        rules = (
            AssistantRule.objects.using(database).filter(tenant=tenant).order_by("position", "id")
        )
        text = "\n\n".join(rule.text for rule in rules)
        if text:
            tenant.assistant_instructions = text[:4000]
            tenant.save(using=database, update_fields=["assistant_instructions"])


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0008_assistantrule")]

    operations = [
        migrations.RunSQL(ENABLE_RLS, reverse_sql=DISABLE_RLS),
        migrations.RunPython(split_existing_instructions, rejoin_into_instructions),
    ]
