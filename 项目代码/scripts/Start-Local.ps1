param([switch]$DependenciesOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$local = Join-Path $root '.local'
$runtime = Join-Path $env:USERPROFILE '.cache/fulfillment-m0'
if (!(Test-Path -LiteralPath (Join-Path $runtime 'tools/mysql-8.4.6-winx64/bin/mysqld.exe'))) { throw 'Run Bootstrap-Local.ps1 first.' }

function Start-OwnedProcess($Name, $Port, $Exe, $Arguments, $Directory) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (!$process.CommandLine -or (!$process.CommandLine.Contains($root) -and !$process.CommandLine.Contains($runtime))) {
            throw "Port $Port is occupied by another program; it will not be stopped."
        }
        $listener.OwningProcess | Set-Content (Join-Path $local "$Name.pid")
        Write-Host "$Name already listening on $Port"
        return
    }
    $p = Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $local "$Name-out.log") -RedirectStandardError (Join-Path $local "$Name-error.log")
    $p.Id | Set-Content (Join-Path $local "$Name.pid")
    $deadline = (Get-Date).AddSeconds(55)
    do {
        Start-Sleep -Milliseconds 500
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) {
            $listener.OwningProcess | Set-Content (Join-Path $local "$Name.pid")
            Write-Host "$Name listening on $Port"
            return
        }
    } while ((Get-Date) -lt $deadline -and !(Get-Process -Id $p.Id -ErrorAction SilentlyContinue).HasExited)
    throw "$Name did not start. Inspect .local/$Name-out.log and .local/$Name-error.log."
}

$ascii = $runtime.Replace('\','/')
$config = Join-Path $runtime 'mysql.ini'
@"
[mysqld]
basedir=$ascii/tools/mysql-8.4.6-winx64
datadir=$ascii/mysql-data
port=33306
bind-address=127.0.0.1
mysqlx=0
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
innodb-buffer-pool-size=128M
log-error=$ascii/mysql-error.log
"@ | Set-Content -LiteralPath $config -Encoding utf8NoBOM
Start-OwnedProcess 'mysql' 33306 (Join-Path $runtime 'tools/mysql-8.4.6-winx64/bin/mysqld.exe') ('--defaults-file="'+$config+'"') $runtime
$marker = Join-Path $local 'mysql-root-needs-password'
if (Test-Path -LiteralPath $marker) {
    & (Join-Path $runtime 'tools/mysql-8.4.6-winx64/bin/mysql.exe') --no-defaults --host=127.0.0.1 --port=33306 --user=root -e "ALTER USER 'root'@'localhost' IDENTIFIED BY 'local-root-dev'"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to set disposable local root password.' }
    # Rename only the known marker, so bootstrap will never try to change an existing password.
    Move-Item -LiteralPath $marker -Destination (Join-Path $local 'mysql-root-password-initialized')
}
$redis = Get-ChildItem -LiteralPath (Join-Path $local 'tools') -Recurse -Filter redis-server.exe | Select-Object -First 1
$redisData = Join-Path $runtime 'redis-data'
New-Item -ItemType Directory -Force -Path $redisData | Out-Null
Start-OwnedProcess 'redis' 36379 $redis.FullName ('--bind 127.0.0.1 --port 36379 --dir "'+$redisData.Replace('\','/')+'" --save "60 1" --appendonly yes --appendfsync everysec') $redis.DirectoryName
& (Join-Path $PSScriptRoot 'Start-Messaging.ps1')
if ($DependenciesOnly) { return }
$jar = Join-Path $root 'backend/yudao-server/target/yudao-server.jar'
if (!(Test-Path -LiteralPath $jar)) { throw 'Build backend first (scripts/Build.ps1).' }
# Run a copy: Windows locks an open jar and otherwise prevents Maven repackage.
$runtimeJar = Join-Path $local 'backend-run.jar'
if (!(Get-NetTCPConnection -State Listen -LocalPort 48080 -ErrorAction SilentlyContinue)) {
    Copy-Item -LiteralPath $jar -Destination $runtimeJar
}
$profile = Join-Path $root 'backend/yudao-server/src/main/resources/application-fulfillment.yaml'
Start-OwnedProcess 'backend' 48080 (Get-Command java).Source `
    ('-Xms256m -Xmx1024m -Dfile.encoding=UTF-8 -Duser.timezone=Asia/Shanghai -jar "'+$runtimeJar+'" --spring.profiles.active=fulfillment --fulfillment.messages.enabled=true --fulfillment.jobs.enabled=true --spring.config.additional-location="file:'+ $profile.Replace('\','/')+'"') (Join-Path $root 'backend')
$vite = Join-Path $root 'frontend/node_modules/vite/bin/vite.js'
Start-OwnedProcess 'frontend' 15173 (Get-Command node).Source ('--max-old-space-size=4096 "'+$vite+'" --mode fulfillment --host 127.0.0.1 --strictPort') (Join-Path $root 'frontend')
Write-Host 'Open http://127.0.0.1:15173 ; tenant: 芋道源码 ; admin / admin123 (local demo only)'
