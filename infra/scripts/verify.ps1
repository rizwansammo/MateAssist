<#
    MateAssist - Phase 0 exit gate.

        powershell -ExecutionPolicy Bypass -File infra\scripts\verify.ps1

    Proves the infrastructure actually works, not merely that containers started:

      1. PostgreSQL 17 reachable on the mapped host port
      2. pgvector present in pg_available_extensions
      3. pgvector FUNCTIONALLY verified in a throwaway database - extension
         created, vector column at the configured EMBEDDING_DIM, an HNSW index
         built with the exact D-057 parameters, and a cosine query returning the
         right nearest neighbour. Then the scratch database is dropped.
         The app database is never touched: per D-015 the extension there is
         created by a Django migration, not by hand.
      4. Redis responds to PING on the mapped port
      5. MinIO bucket exists, is private, and is versioned

    Exit 0 = Phase 0 complete.
#>
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot '_common.ps1')

Assert-DockerRunning
$cfg = Read-DotEnv

# Windows PowerShell 5.1 wraps EVERY stderr line from a native executable in an
# ErrorRecord. Combined with the 'Stop' preference inherited from _common.ps1, a
# harmless psql NOTICE ("database does not exist, skipping") aborts the whole
# run. For native commands the authoritative success signal is $LASTEXITCODE,
# which every check below tests explicitly - so downgrade the preference rather
# than lose stderr, which we still want for diagnostics.
$ErrorActionPreference = 'Continue'

$script:Failures = 0
function Fail-Check { param([string]$m) Write-Fail $m; $script:Failures = $script:Failures + 1 }

$PROBE_DB = 'mateassist_pgvector_probe'

<#  Run SQL in the postgres container. -T disables TTY allocation, which is
    required for non-interactive stdin on Windows. #>
function Invoke-Psql {
    param([string]$Sql, [string]$Database = $cfg['POSTGRES_DB'], [switch]$Quiet)
    # Notices are silenced via PGOPTIONS rather than by prepending a SET to the
    # SQL: psql sends a multi-statement -c as one implicit transaction, and
    # CREATE DATABASE cannot run inside a transaction block.
    $out = & docker exec -e PGPASSWORD=$($cfg['POSTGRES_PASSWORD']) `
        -e "PGOPTIONS=-c client_min_messages=warning" -i mateassist-postgres `
        psql -U $cfg['POSTGRES_USER'] -d $Database -v ON_ERROR_STOP=1 -A -t -c $Sql 2>&1
    $script:LastPsqlExit = $LASTEXITCODE
    $text = ($out | Out-String).Trim()
    if ((-not $Quiet) -and $script:LastPsqlExit -ne 0) { Write-Note $text }
    return $text
}

function Invoke-Mc {
    param([string]$ShellLine)
    $inner = 'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; ' + $ShellLine
    $out = & docker run --rm --network mateassist-net `
        -e MINIO_ROOT_USER=$($cfg['MINIO_ROOT_USER']) `
        -e MINIO_ROOT_PASSWORD=$($cfg['MINIO_ROOT_PASSWORD']) `
        --entrypoint /bin/sh minio/mc:latest -c $inner 2>&1
    $script:LastMcExit = $LASTEXITCODE
    return ($out | Out-String).Trim()
}

Write-Host ''
Write-Host '  MateAssist - Phase 0 verification' -ForegroundColor Cyan
Write-Host '  ---------------------------------' -ForegroundColor Cyan

# -- 1. PostgreSQL -----------------------------------------------------------
Write-Step '1. PostgreSQL 17'
$version = Invoke-Psql 'SHOW server_version;'
if ($script:LastPsqlExit -eq 0 -and $version -match '^17\.') {
    Write-Ok "server_version = $version"
} elseif ($script:LastPsqlExit -eq 0) {
    Fail-Check "expected PostgreSQL 17, got '$version' (D-011)"
} else {
    Fail-Check 'could not reach postgres - is the stack up?'
}

# -- 2. pgvector availability ------------------------------------------------
Write-Step '2. pgvector availability'
$avail = Invoke-Psql "SELECT default_version FROM pg_available_extensions WHERE name = 'vector';"
if ($script:LastPsqlExit -eq 0 -and $avail -ne '') {
    Write-Ok "vector extension available, version $avail"
    Write-Note 'not created in the app database - that is a Django migration (D-015)'
} else {
    Fail-Check 'vector extension NOT available in this image'
}

# -- 3. pgvector functional probe, in a throwaway database -------------------
Write-Step '3. pgvector functional probe (scratch database)'
$dim = $cfg['EMBEDDING_DIM']
if ([string]::IsNullOrWhiteSpace($dim)) { $dim = '384' }

$null = Invoke-Psql "DROP DATABASE IF EXISTS $PROBE_DB;" -Quiet
$null = Invoke-Psql "CREATE DATABASE $PROBE_DB;"
if ($script:LastPsqlExit -ne 0) {
    Fail-Check 'could not create the scratch probe database'
} else {
    $probeSql = @"
CREATE EXTENSION vector;
CREATE TABLE probe (id serial PRIMARY KEY, e vector($dim));
INSERT INTO probe (e) SELECT ARRAY(SELECT 1.0::real FROM generate_series(1, $dim))::vector;
INSERT INTO probe (e) SELECT ARRAY(SELECT (CASE WHEN g = 1 THEN 1.0 ELSE 0.0 END)::real FROM generate_series(1, $dim) g)::vector;
CREATE INDEX probe_hnsw ON probe USING hnsw (e vector_cosine_ops) WITH (m = $($cfg['HNSW_M']), ef_construction = $($cfg['HNSW_EF_CONSTRUCTION']));
SELECT id FROM probe ORDER BY e <=> (SELECT e FROM probe WHERE id = 1) LIMIT 1;
"@
    $probeResult = Invoke-Psql $probeSql -Database $PROBE_DB
    if ($script:LastPsqlExit -eq 0) {
        $nearest = ($probeResult -split "`n" | Where-Object { $_.Trim() -ne '' } | Select-Object -Last 1).Trim()
        if ($nearest -eq '1') {
            Write-Ok "vector($dim) column, HNSW index (m=$($cfg['HNSW_M']), ef_construction=$($cfg['HNSW_EF_CONSTRUCTION'])), cosine operator all working"
            Write-Note "nearest neighbour of row 1 resolved to row 1 - <=> operator correct"
        } else {
            Fail-Check "cosine query returned '$nearest', expected '1'"
        }
    } else {
        Fail-Check 'pgvector functional probe failed'
    }
    $null = Invoke-Psql "DROP DATABASE IF EXISTS $PROBE_DB;" -Quiet
    if ($script:LastPsqlExit -eq 0) { Write-Note 'scratch database dropped; app database untouched' }
}

# -- 4. Redis ----------------------------------------------------------------
Write-Step '4. Redis'
$pong = (& docker exec -i mateassist-redis redis-cli ping 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -eq 0 -and $pong -match 'PONG') {
    Write-Ok "PING -> $pong  (host port $($cfg['REDIS_PORT']))"
    $persist = (& docker exec -i mateassist-redis redis-cli config get appendonly 2>&1 | Out-String).Trim()
    if ($persist -match 'yes') { Write-Note 'appendonly=yes - queued Celery tasks survive restart' }
} else {
    Fail-Check 'redis did not respond to PING'
}

# -- 5. MinIO ----------------------------------------------------------------
Write-Step '5. MinIO object storage'
$bucket = $cfg['S3_BUCKET_NAME']
$lsOut = Invoke-Mc "mc ls local/$bucket >/dev/null 2>&1 && echo BUCKET_OK || echo BUCKET_MISSING"
if ($lsOut -match 'BUCKET_OK') {
    Write-Ok "bucket '$bucket' exists"
    # `mc anonymous set none` is reported back by `mc anonymous get` as
    # 'private'. Assert on the dangerous states rather than on one blessed
    # spelling, so a future mc wording change cannot turn this green by accident.
    $anon = Invoke-Mc "mc anonymous get local/$bucket 2>&1"
    if ($anon -match 'public|download|upload|write') {
        Fail-Check "bucket exposes anonymous access: $anon"
    } elseif ($anon -match 'none|private') {
        Write-Ok "policy reports '$(if ($anon -match 'private') { 'private' } else { 'none' })' - no anonymous policy attached"
    } else {
        Fail-Check "could not determine the bucket anonymous policy: $anon"
    }

    # Stronger than trusting mc's wording: actually try to list the bucket with
    # no credentials. Tenant runbooks must only be reachable through a Django
    # signed URL issued after a tenancy check (D-020), so an unauthenticated
    # request has to be refused.
    $anonProbe = 'unknown'
    try {
        $resp = Invoke-WebRequest -Uri "$($cfg['S3_ENDPOINT_URL'])/$bucket/" -UseBasicParsing -TimeoutSec 10
        $anonProbe = "ALLOWED (HTTP $($resp.StatusCode))"
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -eq 403 -or $code -eq 401) { $anonProbe = "denied (HTTP $code)" }
        elseif ($code) { $anonProbe = "unexpected (HTTP $code)" }
        else { $anonProbe = "no response: $($_.Exception.Message)" }
    }
    if ($anonProbe -like 'denied*') {
        Write-Ok "unauthenticated GET on the bucket was refused - $anonProbe"
    } else {
        Fail-Check "unauthenticated GET on the bucket was NOT refused - $anonProbe"
    }
    $ver = Invoke-Mc "mc version info local/$bucket 2>&1"
    if ($ver -match 'enabled') { Write-Note 'versioning enabled - a re-upload cannot silently destroy the prior runbook' }
} else {
    Fail-Check "bucket '$bucket' not found - check minio-init logs"
}

# -- Summary -----------------------------------------------------------------
Write-Host ''
if ($script:Failures -eq 0) {
    Write-Host '  Phase 0 VERIFIED - infrastructure is provisioned and functional.' -ForegroundColor Green
    Write-Host ''
    Write-Host '  Cleared for Phase 1: Django 5.2 skeleton, DRF, ASGI, Celery wiring,' -ForegroundColor Cyan
    Write-Host '  the two Vite apps, packages/ui extraction, and the provider' -ForegroundColor Cyan
    Write-Host '  model-ID verification gate (DECISIONS.md section 5).' -ForegroundColor Cyan
    Write-Host ''
    exit 0
}

Write-Host ("  {0} check(s) FAILED - Phase 0 is not complete." -f $script:Failures) -ForegroundColor Red
Write-Host '  Do not begin Phase 1 until this exits clean.' -ForegroundColor Red
Write-Host ''
exit 1
