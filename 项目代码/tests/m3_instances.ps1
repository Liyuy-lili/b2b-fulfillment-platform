param([string[]]$TestFiles=@('m3_acceptance.py','m3_permissions.py'),[string]$Python='C:\veighna_studio\python.exe',[switch]$KeepRunning,[switch]$FaultDuringErp)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$jar=Join-Path $projectRoot '.local/backend-run.jar'
$oldPort=$env:APP_PORT
$ownedProcesses=[System.Collections.Generic.List[System.Diagnostics.Process]]::new()
function Start-TestInstance([int]$Port,[string]$Name,[string]$Profiles) {
    $env:APP_PORT=[string]$Port
    $listener=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $owned=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (!$owned.CommandLine.Contains($jar) -or !$owned.CommandLine.Contains("$Name-app.log")) { throw "Port $Port belongs to another process" }
        $process=Get-Process -Id $listener.OwningProcess
    } else {
        $arguments='-Xms128m -Xmx768m -Dfile.encoding=UTF-8 -Duser.timezone=Asia/Shanghai -jar "'+$jar+'" --spring.profiles.active='+$Profiles+' --logging.file.name=../.local/'+$Name+'-app.log'
        if ($Port -eq 48083 -and $FaultDuringErp) { $arguments+=' --fulfillment.test.fail-during-erp=true' }
        $process=Start-Process -FilePath (Get-Command java).Source -ArgumentList $arguments -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot ".local/$Name-out.log") -RedirectStandardError (Join-Path $projectRoot ".local/$Name-error.log")
    }
    $ownedProcesses.Add($process)
    $ready=$false
    $deadline=(Get-Date).AddSeconds(60)
    do {
        try {
            $login=Invoke-RestMethod "http://127.0.0.1:$Port/admin-api/system/auth/login" -Method Post -Headers @{'tenant-id'='1'} -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}' -TimeoutSec 2
            if ($login.code -eq 0) { $ready=$true;break }
        } catch {}
        if ($process.HasExited) { throw "$Name exited; inspect its logs" }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    if (!$ready) { throw "$Name login did not become ready" }
}
try {
    Start-TestInstance 48082 'm3-secondary' 'fulfillment'
    Start-TestInstance 48083 'm3-fault' 'fulfillment,fulfillment-fault-test'
    $listeners=@(Get-NetTCPConnection -State Listen -LocalPort 48080,48082,48083 | Select-Object LocalPort,OwningProcess)
    if (@($listeners.OwningProcess | Select-Object -Unique).Count -ne 3) { throw 'Three distinct JVMs required' }
    $evidenceName=if ($FaultDuringErp) { 'M3-erp-failure-instances.json' } else { 'M3-instances.json' }
    if ($env:M3_INSTANCES_EVIDENCE) { $evidenceName=$env:M3_INSTANCES_EVIDENCE }
    [ordered]@{run_at=(Get-Date).ToString('o');listeners=$listeners;database='fulfillment';redis_database=0;fault_profile_port=48083;fault_during_erp=[bool]$FaultDuringErp;tests=$TestFiles} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $projectRoot "../学习资料/10-验收证据/$evidenceName") -Encoding utf8NoBOM
    foreach ($test in $TestFiles) {
        if ($test -notmatch '^m3_[a-z_]+\.py$') { throw 'Only named M3 tests accepted' }
        & $Python (Join-Path $PSScriptRoot $test)
        if ($LASTEXITCODE -ne 0) { throw "M3 test failed: $test" }
    }
} finally {
    if (!$KeepRunning) {
        foreach ($process in $ownedProcesses) {
            if (!$process.HasExited) {
                $owned=Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
                if ($owned.CommandLine -and $owned.CommandLine.Contains($jar)) { Stop-Process -Id $process.Id;$process.WaitForExit() }
                else { Write-Warning 'PID ownership changed; test process not stopped' }
            }
        }
    }
    $env:APP_PORT=$oldPort
}
