<#
    MateAssist - Phase 0 preflight.

    Checks every prerequisite before `up.ps1` touches anything. Reports the full
    picture in one pass rather than failing on the first problem, so you get one
    complete to-do list instead of a game of whack-a-mole.

    Exit 0 = ready to provision. Exit 1 = blockers listed.

        powershell -ExecutionPolicy Bypass -File infra\scripts\preflight.ps1
#>
[CmdletBinding()]
param()

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$script:Blockers = New-Object System.Collections.Generic.List[string]
$script:Warnings = New-Object System.Collections.Generic.List[string]

function Report {
    param([string]$Name, [string]$State, [string]$Detail)
    $colour = 'DarkGray'
    if ($State -eq 'OK')    { $colour = 'Green' }
    if ($State -eq 'WARN')  { $colour = 'Yellow' }
    if ($State -eq 'BLOCK') { $colour = 'Red' }
    Write-Host ('  {0,-6} {1,-26} {2}' -f $State, $Name, $Detail) -ForegroundColor $colour
}

Write-Host ''
Write-Host '  MateAssist - Phase 0 preflight' -ForegroundColor Cyan
Write-Host '  ------------------------------' -ForegroundColor Cyan

# -- Python 3.12 (D-001) -----------------------------------------------------
$py312 = $null
$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    $listed = & py -0p 2>&1 | Out-String
    if ($listed -match '3\.12') { $py312 = 'py -3.12' }
}
if (-not $py312) {
    $direct = Get-Command python3.12 -ErrorAction SilentlyContinue
    if ($direct) { $py312 = $direct.Source }
}
if ($py312) {
    Report 'Python 3.12' 'OK' $py312
} else {
    Report 'Python 3.12' 'BLOCK' 'not installed - winget install Python.Python.3.12'
    $script:Blockers.Add('Python 3.12 missing (D-001). Run: winget install --id Python.Python.3.12 --scope user')
}

# -- Docker ------------------------------------------------------------------
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Report 'Docker CLI' 'BLOCK' 'not installed'
    $script:Blockers.Add('Docker Desktop missing (D-010). See docs/PHASE-0.md section 2.')
} else {
    Report 'Docker CLI' 'OK' $docker.Source
    $null = & docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report 'Docker engine' 'OK' 'running'
        $composeProbe = & docker compose version 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) {
            Report 'Compose plugin' 'OK' ($composeProbe.Trim() -split "`n")[0]
        } else {
            Report 'Compose plugin' 'BLOCK' 'docker compose unavailable'
            $script:Blockers.Add('docker compose v2 plugin unavailable.')
        }
    } else {
        Report 'Docker engine' 'BLOCK' 'installed but not running - start Docker Desktop'
        $script:Blockers.Add('Docker engine not running. Start Docker Desktop and re-run preflight.')
    }
}

# -- WSL2 - the hard prerequisite for Docker on Windows 11 Home --------------
$wslOk = $false
$wslCmd = Get-Command wsl -ErrorAction SilentlyContinue
if ($wslCmd) {
    $null = & wsl --status 2>&1
    if ($LASTEXITCODE -eq 0) { $wslOk = $true }
}
if ($wslOk) {
    Report 'WSL2' 'OK' 'installed'
} else {
    Report 'WSL2' 'BLOCK' 'not installed - Docker Desktop cannot run without it'
    $script:Blockers.Add('WSL2 missing. Run AS ADMINISTRATOR: wsl --install   (requires a reboot)')
}

# -- .env --------------------------------------------------------------------
$envFile = Join-Path $Root '.env'
if (Test-Path $envFile) {
    # Comment lines carry the <generate> convention as documentation - ignore them.
    $unfilled = Select-String -LiteralPath $envFile -Pattern '<generate>' -SimpleMatch -ErrorAction SilentlyContinue |
        Where-Object { -not $_.Line.TrimStart().StartsWith('#') }
    if ($unfilled) {
        Report '.env' 'BLOCK' ("{0} unfilled placeholder(s)" -f $unfilled.Count)
        $script:Blockers.Add('.env has unfilled <generate> placeholders. Run infra\scripts\generate-secrets.ps1 -Force')
    } else {
        Report '.env' 'OK' 'present, all secrets filled'
    }
    $boot = Select-String -LiteralPath $envFile -Pattern '^(DEEPSEEK|GEMINI)_API_KEY_BOOTSTRAP=\s*$' -ErrorAction SilentlyContinue
    if ($boot) {
        Report 'Provider keys' 'WARN' 'bootstrap keys blank - fine until Phase 4 (O-3)'
        $script:Warnings.Add('DEEPSEEK/GEMINI bootstrap keys are blank. Required before the Phase 1 verification gate.')
    } else {
        Report 'Provider keys' 'OK' 'bootstrap keys present'
    }
} else {
    Report '.env' 'BLOCK' 'missing'
    $script:Blockers.Add('.env missing. Run: powershell -File infra\scripts\generate-secrets.ps1')
}

# -- Host ports the containers will bind -------------------------------------
# Keys are strings deliberately. An OrderedDictionary with Int32 keys resolves
# $map[5433] against the integer INDEX overload, not the key, and silently
# returns $null instead of the label.
$portMap = [ordered]@{
    '5433' = 'postgres  (container 5432)'
    '6380' = 'redis     (container 6379)'
    '9000' = 'minio api'
    '9001' = 'minio console'
}
foreach ($port in $portMap.Keys) {
    $busy = Get-NetTCPConnection -LocalPort ([int]$port) -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        $owner = (Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Report ("port $port") 'BLOCK' ("in use by '{0}' - {1}" -f $owner, $portMap[$port])
        $script:Blockers.Add("Host port $port is occupied by '$owner'. Stop it or remap in .env.")
    } else {
        Report ("port $port") 'OK' $portMap[$port]
    }
}

# -- Native services we deliberately route around (amendment A-001) ----------
foreach ($pair in @(@(5432, 'postgresql-x64-17'), @(6379, 'redis-server'))) {
    $busy = Get-NetTCPConnection -LocalPort $pair[0] -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        Report ("port " + $pair[0]) 'WARN' ("native {0} - expected; MateAssist avoids this port" -f $pair[1])
    }
}

Write-Host ''
if ($script:Blockers.Count -eq 0) {
    Write-Host '  Preflight clean - safe to run up.ps1' -ForegroundColor Green
    if ($script:Warnings.Count -gt 0) {
        Write-Host ''
        Write-Host '  Non-blocking notes:' -ForegroundColor Yellow
        foreach ($w in $script:Warnings) { Write-Host "    - $w" -ForegroundColor Yellow }
    }
    Write-Host ''
    exit 0
}

Write-Host ("  {0} blocker(s) - provisioning cannot proceed:" -f $script:Blockers.Count) -ForegroundColor Red
Write-Host ''
$i = 1
foreach ($b in $script:Blockers) {
    Write-Host ("    {0}. {1}" -f $i, $b) -ForegroundColor Red
    $i = $i + 1
}
Write-Host ''
Write-Host '  Full remediation steps: docs\PHASE-0.md' -ForegroundColor Yellow
Write-Host ''
exit 1
