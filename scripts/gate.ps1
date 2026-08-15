# The phase gate. Run this before pushing; it must exit 0.
#
# Every step below mirrors .github/workflows/ci.yml exactly - same command, same
# working directory, same order. That is the whole point of the file.
#
# It exists because a hand-typed gate drifted from CI and let a failure through.
# `black --check backend` from the repo root passes while `black --check .` from
# backend/ fails, because black resolves its configuration and its default
# exclusions relative to where it is invoked. One character of difference, one
# red build. Typing the commands from memory each time guarantees that recurs;
# a script cannot forget which directory it was supposed to be in.
#
# Keep this in step with ci.yml. If a step is added there and not here, the gate
# stops meaning "CI will pass" and starts meaning "some of CI will pass".

# Continue, NOT Stop. Under PowerShell 5.1 a native executable writing to stderr
# becomes a terminating ErrorRecord when this is "Stop" - and black, ruff and
# npm all write ordinary progress output there. The first run of this script
# reported "GATE FAILED: Format (black)" while black itself was exiting 0.
#
# A gate that cries wolf is worse than no gate: it trains you to ignore it. Exit
# codes are the only failure signal here.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "No virtualenv at backend\.venv - create it first." -ForegroundColor Red
    exit 1
}

$failed = @()

function Step {
    param([string]$Name, [string]$Directory, [scriptblock]$Body)

    Write-Host ""
    Write-Host "-> $Name" -ForegroundColor Cyan
    Push-Location $Directory
    $global:LASTEXITCODE = 0
    try {
        & $Body
        # $LASTEXITCODE is the whole verdict. Native tools do not throw, and
        # their stderr output is not a failure - see the note at the top.
        if ($LASTEXITCODE -ne 0) {
            $script:failed += $Name
            Write-Host "   FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
        }
    }
    catch {
        # Only reachable for real PowerShell faults - a missing executable, a
        # bad path - never for a tool that merely printed to stderr.
        $script:failed += $Name
        Write-Host "   FAILED: $_" -ForegroundColor Red
    }
    finally {
        Pop-Location
    }
}

$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Step "Lint (ruff)" $backend { & $python -m ruff check . }

# --exclude "\.venv" and the backend working directory are both load-bearing.
Step "Format (black)" $backend { & $python -m black --check . --exclude "\.venv" }

Step "Django checks" $backend {
    & $python manage.py check
    if ($LASTEXITCODE -ne 0) { return }
    & $python manage.py makemigrations --check --dry-run
}

Step "Tests" $backend { & $python -m pytest -q }

Step "Design system guard (D-100)" $frontend { npm run lint:radius }

Step "Build both bundles" $frontend { npm run build }

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "GATE FAILED: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "GATE PASSED - CI should be green." -ForegroundColor Green
exit 0
