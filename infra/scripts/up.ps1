<#
    MateAssist - bring up the local infrastructure (D-010).

        powershell -ExecutionPolicy Bypass -File infra\scripts\up.ps1

    Runs preflight first unless -SkipPreflight. Waits for postgres and redis to
    report healthy and for the minio-init bucket bootstrap to exit cleanly, so a
    green finish means the stack is genuinely usable - not merely started.
#>
[CmdletBinding()]
param([switch]$SkipPreflight, [int]$TimeoutSeconds = 180)

. (Join-Path $PSScriptRoot '_common.ps1')

# See the note in verify.ps1: PS 5.1 turns native stderr into ErrorRecords, and
# `docker inspect` on a container that has not been created yet writes to stderr.
# Under the inherited 'Stop' preference that aborts the wait loop instead of
# retrying. Every check here tests $LASTEXITCODE explicitly.
$ErrorActionPreference = 'Continue'

if (-not $SkipPreflight) {
    Write-Step 'Preflight'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'preflight.ps1')
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host '  Aborting: preflight found blockers.' -ForegroundColor Red
        Write-Host ''
        exit 1
    }
}

Assert-DockerRunning

Write-Step 'Pulling images'
$null = Invoke-Compose pull --quiet
if ($LASTEXITCODE -ne 0) { Write-Note 'pull reported a non-zero exit; continuing with any cached images' }

Write-Step 'Starting services'
$code = Invoke-Compose up -d --remove-orphans
if ($code -ne 0) {
    Write-Fail 'docker compose up failed'
    exit 1
}

# -- Wait for health rather than assuming it ---------------------------------
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$targets  = @('mateassist-postgres', 'mateassist-redis', 'mateassist-minio')

Write-Step 'Waiting for health checks'
foreach ($name in $targets) {
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        $state = & docker inspect --format '{{.State.Health.Status}}' $name 2>&1
        if ($LASTEXITCODE -eq 0) {
            $state = ($state | Out-String).Trim()
            if ($state -eq 'healthy') { $healthy = $true; break }
            if ($state -eq 'unhealthy') { break }
        }
        Start-Sleep -Seconds 3
    }
    if ($healthy) {
        Write-Ok "$name healthy"
    } else {
        Write-Fail "$name did not become healthy"
        Write-Note "docker logs $name --tail 50"
        exit 1
    }
}

# -- minio-init is a one-shot: exit code 0 and status 'exited' is success -----
Write-Step 'Bucket bootstrap'
$initDone = $false
while ((Get-Date) -lt $deadline) {
    $status = (& docker inspect --format '{{.State.Status}}' mateassist-minio-init 2>&1 | Out-String).Trim()
    if ($status -eq 'exited') {
        $rc = (& docker inspect --format '{{.State.ExitCode}}' mateassist-minio-init 2>&1 | Out-String).Trim()
        if ($rc -eq '0') { $initDone = $true }
        break
    }
    Start-Sleep -Seconds 2
}
if ($initDone) {
    Write-Ok 'bucket created and set private'
} else {
    Write-Fail 'minio-init did not complete cleanly'
    Write-Note 'docker logs mateassist-minio-init'
    exit 1
}

$cfg = Read-DotEnv
Write-Host ''
Write-Host '  Stack up.' -ForegroundColor Green
Write-Host ''
Write-Host ('    postgres        127.0.0.1:{0}   db={1} user={2}' -f $cfg['POSTGRES_PORT'], $cfg['POSTGRES_DB'], $cfg['POSTGRES_USER'])
Write-Host ('    redis           127.0.0.1:{0}' -f $cfg['REDIS_PORT'])
Write-Host ('    minio api       {0}' -f $cfg['S3_ENDPOINT_URL'])
Write-Host ('    minio console   http://127.0.0.1:{0}   user={1}' -f $cfg['MINIO_CONSOLE_PORT'], $cfg['MINIO_ROOT_USER'])
Write-Host ('    bucket          {0}' -f $cfg['S3_BUCKET_NAME'])
Write-Host ''
Write-Host '  Next:  powershell -File infra\scripts\verify.ps1' -ForegroundColor Cyan
Write-Host ''
