$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$ports=@(3306,15173,33306,36379,48080,35672,35673,35674,35675)
$listeners=@(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in $ports } | Sort-Object LocalPort -Unique | Select-Object LocalAddress,LocalPort,OwningProcess)
$free=$true
foreach($port in @(48081,48082,48083,15174)) {if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){$free=$false}}
$login=Invoke-RestMethod http://127.0.0.1:48080/admin-api/system/auth/login -Method Post -Headers @{'tenant-id'='1'} -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}'
if($login.code -ne 0){throw 'Final runtime real login failed'}
$jobRuntime=Invoke-RestMethod http://127.0.0.1:48080/admin-api/fulfillment/job/runtime -Headers @{'tenant-id'='1';Authorization=('Bearer '+$login.data.accessToken)}
$front=Invoke-WebRequest http://127.0.0.1:15173/erp/fulfillment-jobs
[ordered]@{run_at=(Get-Date).ToString('o');listeners=$listeners;test_ports_free=$free;backend_login_code=$login.code;backend_runtime=$jobRuntime;frontend_status=$front.StatusCode;probe_note='Authenticated real job runtime; Actuator health is not registered in this baseline.'} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $projectRoot '../学习资料/10-验收证据/M6-runtime.json') -Encoding utf8NoBOM
if($jobRuntime.code -ne 0 -or !$jobRuntime.data.enabled -or $front.StatusCode -ne 200 -or !$free){throw 'Final M6 runtime gate failed'}
