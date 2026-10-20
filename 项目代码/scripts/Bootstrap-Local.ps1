# PowerShell 7. Portable tools only; no Windows service or global PATH changes.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$local = Join-Path $root '.local'
$lock = Get-Content -Raw (Join-Path $root 'docs/baseline.lock.json') | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path (Join-Path $local 'downloads') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $local 'tools') | Out-Null
foreach ($name in @('mysql','redis')) {
    $tool = $lock.tools | Where-Object name -EQ $name
    $archive = Join-Path $local "downloads/$name.zip"
    if (!(Test-Path -LiteralPath $archive)) { Invoke-WebRequest $tool.url -OutFile $archive }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tool.sha256) { throw "$name archive checksum mismatch" }
    $executable = if ($name -eq 'mysql') { Join-Path $local 'tools/mysql-8.4.6-winx64/bin/mysqld.exe' } else { Join-Path $local 'tools/Redis-7.2.8-Windows-x64-msys2/redis-server.exe' }
    if (!(Test-Path -LiteralPath $executable)) {
        # Python zipfile avoids the slow per-file PowerShell Expand-Archive path.
        & python -m zipfile -e $archive (Join-Path $local 'tools')
        if ($LASTEXITCODE -ne 0) { throw "Failed to extract $name" }
    }
}
# MySQL on this Windows installation misreads the Chinese executable path.
$runtime = Join-Path $env:USERPROFILE '.cache/fulfillment-m0'
if (Test-Path -LiteralPath $runtime) {
    $item = Get-Item -LiteralPath $runtime
    if ($item.LinkType -ne 'Junction' -or $item.Target -ne $local) { throw "Runtime path $runtime belongs to another workspace." }
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $runtime) | Out-Null
    New-Item -ItemType Junction -Path $runtime -Target $local | Out-Null
}
$data = Join-Path $runtime 'mysql-data'
if (!(Test-Path -LiteralPath (Join-Path $data 'mysql'))) {
    if ((Test-Path -LiteralPath $data) -and (Get-ChildItem -LiteralPath $data -Force)) { throw 'Nonempty uninitialized data directory; inspect manually.' }
    & (Join-Path $runtime 'tools/mysql-8.4.6-winx64/bin/mysqld.exe') --no-defaults --initialize-insecure "--datadir=$data" --console
    if ($LASTEXITCODE -ne 0) { throw 'MySQL initialization failed.' }
    New-Item -ItemType File -Path (Join-Path $local 'mysql-root-needs-password') -Force | Out-Null
}
$prefix = Join-Path $local 'node-tools'
if (!(Test-Path -LiteralPath (Join-Path $prefix 'node_modules/pnpm/bin/pnpm.cjs'))) {
    & npm.cmd install --prefix $prefix pnpm@9.15.9 --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Portable pnpm setup failed.' }
}
Write-Host 'Portable tools ready. Next: ./scripts/Start-Local.ps1 -DependenciesOnly'
