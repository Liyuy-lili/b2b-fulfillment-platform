$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location (Join-Path $root 'backend')
try {
    & ./mvnw.cmd -B -ntp -pl yudao-server -am package -DskipTests
    if ($LASTEXITCODE -ne 0) { throw 'Backend build failed.' }
} finally { Pop-Location }
Push-Location (Join-Path $root 'frontend')
try {
    $pnpm = Join-Path $root '.local/node-tools/node_modules/.bin/pnpm.cmd'
    & $pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed.' }
    & $pnpm run build:fulfillment
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Host 'Build complete. This command skips upstream unit tests; run tests/m0_smoke.py separately for real M0 acceptance.'
