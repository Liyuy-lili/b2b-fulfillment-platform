param([string]$Database='fulfillment_m1_clean_20261017', [string]$Python='C:\veighna_studio\python.exe', [string]$EvidenceFile='M1-clean-acceptance.json',[ValidateRange(1,15)][int]$RedisDatabase=1,[string]$ExtraTest='')
$ErrorActionPreference='Stop'
if ($Database -notmatch '^fulfillment_m[123]_clean_[a-z0-9_]+$') { throw 'Use an independent clean database' }
if ($EvidenceFile -notmatch '^M[123]-[A-Za-z0-9-]+\.json$') { throw 'Use a named evidence file' }
$projectRoot=Split-Path $PSScriptRoot -Parent
if (Get-NetTCPConnection -LocalPort 48081 -State Listen -ErrorAction SilentlyContinue) { throw '48081 is occupied; no process will be stopped' }
$jar=Join-Path $projectRoot '.local/backend-run.jar'
$oldDb=$env:DB_NAME; $oldPort=$env:APP_PORT; $oldApi=$env:API_BASE; $oldEvidence=$env:M1_EVIDENCE
$process=$null
try {
  $env:DB_NAME=$Database; $env:APP_PORT='48081'
  $arguments='-Xms128m -Xmx768m -Dfile.encoding=UTF-8 -Duser.timezone=Asia/Shanghai -jar "'+$jar+'" --spring.profiles.active=fulfillment --spring.data.redis.database='+$RedisDatabase+' --logging.file.name=../.local/m1-clean-app.log'
  $process=Start-Process -FilePath (Get-Command java).Source -ArgumentList $arguments -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot '.local/m1-clean-out.log') -RedirectStandardError (Join-Path $projectRoot '.local/m1-clean-error.log')
  $deadline=(Get-Date).AddSeconds(55)
  $ready=$false
  do {
    try {
      $login=Invoke-RestMethod 'http://127.0.0.1:48081/admin-api/system/auth/login' -Method Post -Headers @{'tenant-id'='1'} -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}' -TimeoutSec 2
      if ($login.code -eq 0) { $ready=$true; break }
    } catch {}
    if ($process.HasExited) { throw 'Clean application exited; inspect .local/m1-clean-out.log' }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  if (!$ready) { throw 'Clean application real login did not become ready' }
  $env:API_BASE='http://127.0.0.1:48081'; $env:M1_EVIDENCE=$EvidenceFile
  & $Python (Join-Path $PSScriptRoot 'm1_acceptance.py')
  if ($LASTEXITCODE -ne 0) { throw 'Clean M1 acceptance failed' }
  if ($ExtraTest) {
    if ($ExtraTest -notmatch '^m[23]_[a-z_]+\.py$') { throw 'Only named M2/M3 extra test accepted' }
    & $Python (Join-Path $PSScriptRoot $ExtraTest)
    if ($LASTEXITCODE -ne 0) { throw 'Clean extra workflow test failed' }
  }
} finally {
  if ($process -and !$process.HasExited) {
    $owned=Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
    if ($owned.CommandLine -and $owned.CommandLine.Contains($jar)) { Stop-Process -Id $process.Id; $process.WaitForExit() }
    else { Write-Warning 'PID ownership changed; process was not stopped' }
  }
  $env:DB_NAME=$oldDb; $env:APP_PORT=$oldPort; $env:API_BASE=$oldApi; $env:M1_EVIDENCE=$oldEvidence
}
