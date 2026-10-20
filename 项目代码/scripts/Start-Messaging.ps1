param()
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'Messaging-Environment.ps1')
if(!(Test-Path -LiteralPath (Join-Path $env:ERLANG_HOME 'bin/erl.exe'))){& (Join-Path $PSScriptRoot 'Bootstrap-Messaging.ps1')}
$listener=Get-NetTCPConnection -State Listen -LocalPort 35672 -ErrorAction SilentlyContinue | Select-Object -First 1
if($listener){
 $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
 if(!$process.CommandLine -or !$process.CommandLine.Contains($messagingRuntime,[StringComparison]::OrdinalIgnoreCase)){throw 'AMQP port belongs to another program'}
 Write-Host 'Project RabbitMQ already listening on 35672';return
}
New-Item -ItemType Directory -Force -Path $env:RABBITMQ_BASE | Out-Null
@'
listeners.tcp.1 = 127.0.0.1:35672
management.tcp.ip = 127.0.0.1
management.tcp.port = 35673
distribution.listener.interface = 127.0.0.1
distribution.listener.port_range.min = 35674
distribution.listener.port_range.max = 35674
default_user = fulfillment
default_pass = fulfillment-mq-dev
default_vhost = fulfillment
disk_free_limit.absolute = 100MB
vm_memory_high_watermark.absolute = 256MiB
log.console = true
log.console.level = info
'@ | Set-Content -LiteralPath ($env:RABBITMQ_CONFIG_FILE+'.conf') -Encoding utf8NoBOM
'[rabbitmq_management].' | Set-Content -LiteralPath $env:RABBITMQ_ENABLED_PLUGINS_FILE -Encoding ascii
$shell=(Get-Process -Id $PID).Path
$run=Join-Path $PSScriptRoot 'Run-Messaging.ps1'
$p=Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-File',('"'+$run+'"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot '.local/rabbitmq-out.log') -RedirectStandardError (Join-Path $projectRoot '.local/rabbitmq-error.log')
$p.Id | Set-Content -LiteralPath (Join-Path $projectRoot '.local/rabbitmq-wrapper.pid')
$deadline=(Get-Date).AddSeconds(55)
do{
 Start-Sleep -Milliseconds 500
 if(Get-NetTCPConnection -State Listen -LocalPort 35672 -ErrorAction SilentlyContinue){Write-Host 'Project RabbitMQ listening on 35672; management loopback 35673';return}
 if($p.HasExited){throw 'RabbitMQ exited; inspect .local/rabbitmq-error.log'}
}while((Get-Date) -lt $deadline)
throw 'RabbitMQ startup exceeded 55s; inspect logs and actual listeners before retrying.'
