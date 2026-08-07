"""Enable pgvector.

D-015: the extension is created by a migration, never by hand. Phase 0's gate
proved the extension *works* in a throwaway database and deliberately left the
application database untouched so this migration remains the only path that
installs it.

VectorExtension issues CREATE EXTENSION IF NOT EXISTS vector, so re-running is
safe. On managed PostgreSQL the database role may lack CREATE EXTENSION rights;
there the provider enables it out of band and this migration is a no-op.
"""

from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    initial = True

    dependencies: list = []

    operations = [
        VectorExtension(),
    ]
