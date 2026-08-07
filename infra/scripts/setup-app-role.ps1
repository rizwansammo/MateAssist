<#
    Create the non-superuser runtime role that RLS depends on (D-020).

        powershell -ExecutionPolicy Bypass -File infra\scripts\setup-app-role.ps1

    WHY THIS EXISTS
    PostgreSQL superusers bypass Row Level Security unconditionally, and table
    OWNERS bypass it unless the table is marked FORCE ROW LEVEL SECURITY. The
    POSTGRES_USER created by the container image is a superuser, so running the
    application as that role would make every RLS policy decorative and the
    D-025 isolation gate would pass while proving nothing.

    So: migrations and platform-admin traffic use the owner role, and all tenant
    traffic connects as mateassist_app, which is NOSUPERUSER and therefore
    subject to policy.

    This is infrastructure, not a migration - the role has to exist before Django
    can open its first connection, so a migration could never create it.

    Idempotent. Safe to re-run.
#>
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Continue'

Assert-DockerRunning
$cfg = Read-DotEnv

$appUser = $cfg['DATABASE_APP_USER']
$appPass = $cfg['DATABASE_APP_PASSWORD']
if ([string]::IsNullOrWhiteSpace($appUser) -or [string]::IsNullOrWhiteSpace($appPass)) {
    Write-Fail 'DATABASE_APP_USER / DATABASE_APP_PASSWORD missing from .env'
    exit 1
}

function Invoke-Psql {
    param([string]$Sql, [string]$Database = $cfg['POSTGRES_DB'])
    $out = & docker exec -e PGPASSWORD=$($cfg['POSTGRES_PASSWORD']) `
        -e "PGOPTIONS=-c client_min_messages=warning" -i mateassist-postgres `
        psql -U $cfg['POSTGRES_USER'] -d $Database -v ON_ERROR_STOP=1 -X -q -c $Sql 2>&1
    $script:Code = $LASTEXITCODE
    return ($out | Out-String).Trim()
}

# Existence is checked from here rather than in a DO block: PL/pgSQL needs
# dollar-quoting, and $$ does not survive PowerShell string interpolation
# intact. Plain statements keep the escaping problem from existing at all.
Write-Step 'Creating the runtime role'
$exists = Invoke-Psql "SELECT 1 FROM pg_roles WHERE rolname = '$appUser';"
$verb = if ($exists -match '1') { 'ALTER' } else { 'CREATE' }
$r = Invoke-Psql "$verb ROLE $appUser LOGIN PASSWORD '$appPass' NOSUPERUSER NOCREATEROLE CREATEDB;"
if ($script:Code -ne 0) { Write-Fail "role $verb failed: $r"; exit 1 }
Write-Ok "$appUser exists, NOSUPERUSER (RLS applies to it)"
Write-Note 'CREATEDB is granted so pytest can build its test database'

Write-Step 'Granting schema and object privileges'
$grants = @"
GRANT CONNECT ON DATABASE $($cfg['POSTGRES_DB']) TO $appUser;
GRANT USAGE, CREATE ON SCHEMA public TO $appUser;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $appUser;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $appUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $appUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO $appUser;
"@
$r = Invoke-Psql $grants
if ($script:Code -ne 0) { Write-Fail "grants failed: $r"; exit 1 }
Write-Ok 'DML on existing and future tables granted'

# pgvector's CREATE EXTENSION needs superuser. Installing it into template1 means
# every database cloned from it - including pytest's throwaway test database -
# already has the type, so the Django migration's IF NOT EXISTS becomes a no-op
# there instead of a permission error. D-015 is unaffected: the migration is
# still the only thing that installs it into the application schema.
Write-Step 'Seeding pgvector into template1 (so test databases inherit it)'
$r = Invoke-Psql 'CREATE EXTENSION IF NOT EXISTS vector;' -Database 'template1'
if ($script:Code -ne 0) { Write-Fail "template1 seeding failed: $r"; exit 1 }
Write-Ok 'template1 carries the vector extension'

Write-Step 'Verifying the role really is subject to RLS'
$check = Invoke-Psql "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = '$appUser';"
if ($check -match 'f') {
    Write-Ok 'confirmed: not superuser, no BYPASSRLS - policies will be enforced'
} else {
    Write-Fail "role can bypass RLS - isolation would be decorative. Got: $check"
    exit 1
}

Write-Host ''
Write-Host '  Runtime role ready.' -ForegroundColor Green
Write-Host ''
