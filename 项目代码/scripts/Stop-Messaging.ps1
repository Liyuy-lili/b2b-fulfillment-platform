param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Messaging-Environment.ps1')
$listener=Get-NetTCPConnection -State Listen -LocalPort 35672 -ErrorAction SilentlyContinue | Select-Object -First 1
if($listener){
$process=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
if(!$process.CommandLine -or !$process.CommandLine.Contains($messagingRuntime,[StringComparison]::OrdinalIgnoreCase)){throw 'RabbitMQ port owner changed; refusing shutdown'}
& (Join-Path $messagingSbin 'rabbitmqctl.bat') -n fulfillment@localhost shutdown
if($LASTEXITCODE -ne 0){throw 'Project RabbitMQ graceful shutdown failed'}
}
$epmdListener=Get-NetTCPConnection -State Listen -LocalPort 35675 -ErrorAction SilentlyContinue | Select-Object -First 1
if($epmdListener){
 $epmdProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$($epmdListener.OwningProcess)"
 if(!$epmdProcess.CommandLine -or !$epmdProcess.CommandLine.Contains($env:ERLANG_HOME,[StringComparison]::OrdinalIgnoreCase)){throw 'Project EPMD owner changed; refusing stop'}
 $epmd=Get-ChildItem -LiteralPath $env:ERLANG_HOME -Directory -Filter 'erts-*' | Select-Object -First 1
 & (Join-Path $epmd.FullName 'bin/epmd.exe') -port 35675 -kill
 if($LASTEXITCODE -ne 0){throw 'Project EPMD still has registered nodes'}
}
