<#
    MateAssist - stop the local infrastructure.

        powershell -File infra\scripts\down.ps1              # stop, keep data
        powershell -File infra\scripts\down.ps1 -DestroyData  # stop and delete volumes

    -DestroyData is irreversible: it deletes the postgres volume (every tenant,
    ticket, document and vector) and the minio volume (every uploaded runbook).
    It prompts for typed confirmation.
#>
[CmdletBinding()]
param([switch]$DestroyData)

. (Join-Path $PSScriptRoot '_common.ps1')

Assert-DockerRunning

if (-not $DestroyData) {
    Write-Step 'Stopping services (data volumes retained)'
    $code = Invoke-Compose down --remove-orphans
    if ($code -ne 0) { Write-Fail 'compose down reported an error'; exit 1 }
    Write-Ok 'stopped - volumes intact, `up.ps1` will restore state'
    Write-Host ''
    exit 0
}

Write-Host ''
Write-Host '  DESTRUCTIVE: this deletes all three data volumes.' -ForegroundColor Red
Write-Host '    mateassist-postgres-data   every tenant, ticket, document, vector' -ForegroundColor Red
Write-Host '    mateassist-minio-data      every uploaded runbook file' -ForegroundColor Red
Write-Host '    mateassist-redis-data      queued and in-flight Celery tasks' -ForegroundColor Red
Write-Host ''
Write-Host '  There is no undo and no backup is taken.' -ForegroundColor Red
Write-Host ''
$answer = Read-Host '  Type DESTROY to proceed, anything else to abort'
if ($answer -ne 'DESTROY') {
    Write-Host ''
    Write-Host '  Aborted - nothing was changed.' -ForegroundColor Green
    Write-Host ''
    exit 0
}

Write-Step 'Removing services and volumes'
$code = Invoke-Compose down --volumes --remove-orphans
if ($code -ne 0) { Write-Fail 'compose down --volumes reported an error'; exit 1 }
Write-Ok 'services and volumes removed'
Write-Note 'next up.ps1 starts from an empty database - Django migrations must re-run'
Write-Host ''
