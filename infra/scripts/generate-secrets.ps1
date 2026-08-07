<#
    MateAssist - generate .env from .env.example with real secrets.

    Fills every <generate> placeholder with cryptographically random material:
      DJANGO_SECRET_KEY      base64, 64 bytes
      MATEASSIST_VAULT_KEY   base64 of exactly 32 raw bytes  (AES-256-GCM KEK, D-071)
      POSTGRES_PASSWORD      URL-safe alphanumeric (it is embedded in DATABASE_URL)
      MINIO_ROOT_PASSWORD    URL-safe alphanumeric, mirrored to S3_SECRET_ACCESS_KEY

    Refuses to overwrite an existing .env unless -Force. Regenerating
    MATEASSIST_VAULT_KEY makes every stored ProviderKey permanently unreadable
    (D-071) - that is why this is opt-in and loud.

        powershell -ExecutionPolicy Bypass -File infra\scripts\generate-secrets.ps1
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Example  = Join-Path $Root '.env.example'
$EnvFile  = Join-Path $Root '.env'

if (-not (Test-Path $Example)) { throw "Missing contract file: $Example" }

if ((Test-Path $EnvFile) -and (-not $Force)) {
    Write-Host ''
    Write-Host '  .env already exists - nothing was changed.' -ForegroundColor Yellow
    Write-Host '  Overwriting it rotates MATEASSIST_VAULT_KEY, which permanently' -ForegroundColor Yellow
    Write-Host '  orphans every API key already stored in the vault (D-071).' -ForegroundColor Yellow
    Write-Host '  Re-run with -Force only if you accept that.' -ForegroundColor Yellow
    Write-Host ''
    exit 0
}

function New-Base64Secret {
    param([int]$Bytes = 32)
    $buf = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buf) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($buf)
}

function New-UrlSafeSecret {
    # Alphanumeric only. This value lands inside DATABASE_URL, where base64's
    # '+', '/' and '=' would need percent-encoding and quietly break parsing.
    param([int]$Length = 40)
    $alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    $buf = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buf) } finally { $rng.Dispose() }
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $buf) { [void]$sb.Append($alphabet[$b % $alphabet.Length]) }
    return $sb.ToString()
}

$djangoSecret = New-Base64Secret -Bytes 64
$vaultKey     = New-Base64Secret -Bytes 32     # must be exactly 32 bytes for AES-256
$pgPassword   = New-UrlSafeSecret -Length 40
$minioSecret  = New-UrlSafeSecret -Length 40

$out = New-Object System.Collections.Generic.List[string]

foreach ($line in (Get-Content -LiteralPath $Example)) {
    $new = $line

    if ($line -match '^DJANGO_SECRET_KEY=')    { $new = "DJANGO_SECRET_KEY=$djangoSecret" }
    elseif ($line -match '^MATEASSIST_VAULT_KEY=') { $new = "MATEASSIST_VAULT_KEY=$vaultKey" }
    elseif ($line -match '^POSTGRES_PASSWORD=') { $new = "POSTGRES_PASSWORD=$pgPassword" }
    elseif ($line -match '^MINIO_ROOT_PASSWORD=') { $new = "MINIO_ROOT_PASSWORD=$minioSecret" }
    # MinIO's root credentials ARE the S3 credentials - these must stay identical
    # or every presigned URL fails with SignatureDoesNotMatch.
    elseif ($line -match '^S3_SECRET_ACCESS_KEY=') { $new = "S3_SECRET_ACCESS_KEY=$minioSecret" }
    elseif ($line -match '^DATABASE_URL=') {
        $new = "DATABASE_URL=postgresql://mateassist:$pgPassword@127.0.0.1:5433/mateassist"
    }

    $out.Add($new)
}

# ASCII, no BOM. python-dotenv and docker compose both choke on a UTF-8 BOM in
# the first key name - it becomes part of the variable name and silently unsets it.
[System.IO.File]::WriteAllLines($EnvFile, $out, (New-Object System.Text.UTF8Encoding($false)))

# Only real assignments matter here. The contract file explains the <generate>
# convention in its own header comments, which must not count as unfilled.
$remaining = Select-String -LiteralPath $EnvFile -Pattern '<generate>' -SimpleMatch -ErrorAction SilentlyContinue |
    Where-Object { -not $_.Line.TrimStart().StartsWith('#') }
if ($remaining) {
    Write-Host ''
    Write-Host '  WARNING: unfilled <generate> placeholders remain:' -ForegroundColor Red
    foreach ($m in $remaining) { Write-Host ("    line {0}: {1}" -f $m.LineNumber, $m.Line) -ForegroundColor Red }
    exit 1
}

Write-Host ''
Write-Host '  Wrote .env with generated secrets.' -ForegroundColor Green
Write-Host '    DJANGO_SECRET_KEY     64 bytes, base64'
Write-Host '    MATEASSIST_VAULT_KEY  32 bytes, base64   (AES-256-GCM KEK)'
Write-Host '    POSTGRES_PASSWORD     40 chars, url-safe (mirrored into DATABASE_URL)'
Write-Host '    MINIO_ROOT_PASSWORD   40 chars, url-safe (mirrored into S3_SECRET_ACCESS_KEY)'
Write-Host ''
Write-Host '  .env is gitignored. Back up MATEASSIST_VAULT_KEY somewhere safe -' -ForegroundColor Yellow
Write-Host '  losing it means re-entering every provider API key by hand.' -ForegroundColor Yellow
Write-Host ''
Write-Host '  Still blank, and required from Phase 4 (open item O-3):'
Write-Host '    DEEPSEEK_API_KEY_BOOTSTRAP   GEMINI_API_KEY_BOOTSTRAP'
Write-Host ''
