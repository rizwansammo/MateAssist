#!/bin/bash
# Create the NOSUPERUSER application role on first boot (D-020).
#
# THIS FILE IS THE ISOLATION GUARANTEE.
#
# Every tenant table carries a row-level security policy, and PostgreSQL exempts
# superusers from RLS unconditionally. If the application connected as
# POSTGRES_USER - the database owner - every policy would remain in place and
# enforce nothing. Isolation would be decorative, all nine D-025 tests would
# still pass, and one workspace could read another's runbooks and spend.
#
# So there are two roles and two Django aliases:
#
#   mateassist_app   NOSUPERUSER. All tenant traffic. Subject to policy.
#   ${POSTGRES_USER} owner. Migrations, and the platform-admin surface, which
#                    must legitimately read across tenants.
#
# Runs only when the data directory is empty - Postgres ignores
# /docker-entrypoint-initdb.d on an existing volume. Re-running is handled
# anyway: the role creation is idempotent.

set -euo pipefail

if [ -z "${APP_DB_PASSWORD:-}" ]; then
    echo "FATAL: APP_DB_PASSWORD is unset. The application role would have no" >&2
    echo "       password, so DATABASE_APP_URL could not authenticate and the" >&2
    echo "       app would fall back to nothing at all. Refusing to continue." >&2
    exit 1
fi

APP_USER="${APP_DB_USER:-mateassist_app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${APP_USER}') THEN
            CREATE ROLE ${APP_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}'
                NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS;
        ELSE
            ALTER ROLE ${APP_USER} WITH PASSWORD '${APP_DB_PASSWORD}'
                NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS;
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_USER};
    GRANT USAGE ON SCHEMA public TO ${APP_USER};

    -- Rights on tables that already exist, and on everything migrations create
    -- later. Without the DEFAULT PRIVILEGES line, every future migration would
    -- produce tables the application role cannot read.
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP_USER};
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${APP_USER};

    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO ${APP_USER};
SQL

# The extension has to exist before migration 0002 creates the HNSW index.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "app role ${APP_USER} ready (NOSUPERUSER, NOBYPASSRLS) and pgvector installed"
