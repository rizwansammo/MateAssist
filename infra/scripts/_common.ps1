<#
    Shared helpers for the MateAssist infra scripts. Dot-sourced, not run directly.
#>

$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    return Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

function Get-ComposeFile {
    return Join-Path (Get-RepoRoot) 'infra\docker-compose.yml'
}

function Get-EnvFile {
    return Join-Path (Get-RepoRoot) '.env'
}

<#
    Parse the root .env into a hashtable. The env contract lives at the repo root
    (shared by Django, Celery and compose) rather than beside the compose file,
    so there is exactly one source of truth.
#>
function Read-DotEnv {
    param([string]$Path = (Get-EnvFile))
    if (-not (Test-Path $Path)) { throw "Missing .env at $Path - run infra\scripts\generate-secrets.ps1" }
    $map = @{}
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '') { continue }
        if ($trimmed.StartsWith('#')) { continue }
        $idx = $trimmed.IndexOf('=')
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $val = $trimmed.Substring($idx + 1).Trim()
        if ($val.Length -ge 2) {
            if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
                $val = $val.Substring(1, $val.Length - 2)
            }
        }
        $map[$key] = $val
    }
    return $map
}

<#
    Every compose invocation goes through here so --env-file and -f are never
    forgotten. Returns the raw exit code; callers decide whether it is fatal.
#>
function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $composeArgs = @('compose', '--env-file', (Get-EnvFile), '-f', (Get-ComposeFile)) + $Args
    & docker @composeArgs
    return $LASTEXITCODE
}

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host "  $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  PASS  $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  FAIL  $Message" -ForegroundColor Red
}

function Write-Note {
    param([string]$Message)
    Write-Host "        $Message" -ForegroundColor DarkGray
}

function Assert-DockerRunning {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw 'Docker CLI not found. See docs\PHASE-0.md section 2 for the install path.'
    }
    $null = & docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker engine is not running. Start Docker Desktop, wait for the whale icon to settle, then retry.'
    }
}
