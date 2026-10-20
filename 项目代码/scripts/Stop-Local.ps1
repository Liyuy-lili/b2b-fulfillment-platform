param([switch]$Dependencies)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $env:USERPROFILE '.cache/fulfillment-m0'
$ports = @(15173,48080)
if ($Dependencies) { $ports += @(36379,33306) }
foreach ($port in $ports) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$listener) { continue }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (!$process.CommandLine -or (!$process.CommandLine.Contains($root) -and !$process.CommandLine.Contains($runtime))) { throw "Port $port belongs to another program; refusing to stop it." }
    if ($port -eq 33306) {
        $old = $env:MYSQL_PWD
        try {
            $env:MYSQL_PWD = 'local-root-dev'
            & (Join-Path $runtime 'tools/mysql-8.4.6-winx64/bin/mysqladmin.exe') --no-defaults --host=127.0.0.1 --port=33306 --user=root shutdown
            if ($LASTEXITCODE -ne 0) { throw 'MySQL graceful shutdown failed.' }
        } finally { $env:MYSQL_PWD = $old }
    } elseif ($port -eq 36379) {
        $redisCli = Get-ChildItem -LiteralPath (Join-Path $root '.local/tools') -Recurse -Filter redis-cli.exe | Select-Object -First 1
        & $redisCli.FullName -h 127.0.0.1 -p 36379 shutdown save
        if ($LASTEXITCODE -ne 0) { throw 'Redis graceful shutdown failed.' }
    } else {
        Stop-Process -Id $listener.OwningProcess
    }
    Write-Host "Stopped project listener on $port"
}
if($Dependencies){ & (Join-Path $PSScriptRoot 'Stop-Messaging.ps1') }
