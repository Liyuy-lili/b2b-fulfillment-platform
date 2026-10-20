$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$ports=@(3306,15173,33306,36379,48080,35672,35673,35674,35675)
$listeners=@(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in $ports } | Sort-Object LocalPort -Unique | Select-Object LocalAddress,LocalPort,OwningProcess)
$free=$true
foreach($port in @(48081,48082,48083,15174)){if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){$free=$false}}
$front=Invoke-WebRequest http://127.0.0.1:15173/erp/fulfillment
[ordered]@{run_at=(Get-Date).ToString('o');listeners=$listeners;test_ports_free=$free;main_frontend_status=$front.StatusCode;java_version=(& java -version 2>&1 | Out-String);node_version=(& node --version);powershell_version=$PSVersionTable.PSVersion.ToString()} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $projectRoot '../学习资料/10-验收证据/M7.1-runtime.json') -Encoding utf8NoBOM
if(!$free -or $front.StatusCode -ne 200){throw 'M7.1 runtime cleanup gate failed'}
