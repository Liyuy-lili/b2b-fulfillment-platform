param([string[]]$TestFiles=@('m2_acceptance.py','m2_legacy_inventory.py'),[string]$Python='C:\veighna_studio\python.exe',[switch]$KeepRunning)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$existing=Get-NetTCPConnection -LocalPort 48082 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$jar=Join-Path $projectRoot '.local/backend-run.jar'
$oldPort=$env:APP_PORT
$process=$null
try {
  $env:APP_PORT='48082'
  if ($existing) {
    $owned=Get-CimInstance Win32_Process -Filter "ProcessId=$($existing.OwningProcess)"
    if (!$owned.CommandLine.Contains($jar) -or !$owned.CommandLine.Contains('m2-secondary-app.log')) { throw '48082 belongs to another process' }
    $process=Get-Process -Id $existing.OwningProcess
  } else {
  $process=Start-Process -FilePath (Get-Command java).Source -ArgumentList ('-Xms128m -Xmx768m -Dfile.encoding=UTF-8 -Duser.timezone=Asia/Shanghai -jar "'+$jar+'" --spring.profiles.active=fulfillment --logging.file.name=../.local/m2-secondary-app.log') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot '.local/m2-secondary-out.log') -RedirectStandardError (Join-Path $projectRoot '.local/m2-secondary-error.log')
  }
  $ready=$false;$deadline=(Get-Date).AddSeconds(55)
  do {
    try {
      $login=Invoke-RestMethod 'http://127.0.0.1:48082/admin-api/system/auth/login' -Method Post -Headers @{'tenant-id'='1'} -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}' -TimeoutSec 2
      if ($login.code -eq 0) { $ready=$true; break }
    } catch {}
    if ($process.HasExited) { throw 'Secondary JVM exited; inspect logs' }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  if (!$ready) { throw 'Secondary real login not ready' }
  $listeners=Get-NetTCPConnection -State Listen -LocalPort 48080,48082 | Select-Object LocalPort,OwningProcess
  if (@($listeners.OwningProcess | Select-Object -Unique).Count -ne 2) { throw 'Two distinct JVM processes required' }
  [ordered]@{date='2026-10-18';listeners=@($listeners);database='fulfillment';redis_database=0;tests=$TestFiles} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $projectRoot '../学习资料/10-验收证据/M2-two-instance.json') -Encoding utf8NoBOM
  foreach ($test in $TestFiles) {
    if ($test -notmatch '^m2_[a-z_]+\.py$') { throw 'Only named M2 tests accepted' }
    & $Python (Join-Path $PSScriptRoot $test)
    if ($LASTEXITCODE -ne 0) { throw "M2 test failed: $test" }
  }
} finally {
  if (!$KeepRunning -and $process -and !$process.HasExited) {
    $owned=Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
    if ($owned.CommandLine -and $owned.CommandLine.Contains($jar)) { Stop-Process -Id $process.Id; $process.WaitForExit() }
    else { Write-Warning 'PID ownership changed; secondary process not stopped' }
  }
  $env:APP_PORT=$oldPort
}
