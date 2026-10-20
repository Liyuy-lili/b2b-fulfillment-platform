param([Parameter(Mandatory)][string]$Config)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Release-Environment.ps1')
$root=Split-Path $PSScriptRoot -Parent;Test-ReleaseFiles $root;$c=Read-ReleaseConfig $Config;Set-ReleaseEnvironment $c
foreach($port in @($c.backendPort,$c.frontendPort)){if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){throw ('Release port occupied: '+$port)}}
$data=Join-Path $root 'data';New-Item -ItemType Directory -Force -Path $data,(Join-Path $data 'logs'),(Join-Path $data 'files') | Out-Null
$argsList=@('-Xms128m',('-Xmx'+$c.javaHeapMb+'m'),'-Dfile.encoding=UTF-8','-Duser.timezone=Asia/Shanghai','-jar',(Join-Path $root 'app/backend.jar'),'--spring.profiles.active=fulfillment',('--server.port='+$c.backendPort),('--spring.data.redis.database='+$c.redisDatabase),'--fulfillment.jobs.enabled=true',('--fulfillment.jobs.storage-root='+(Join-Path $data 'files')),'--fulfillment.messages.enabled=true',('--fulfillment.messages.host='+$c.rabbitHost),('--fulfillment.messages.port='+$c.rabbitPort),('--fulfillment.messages.virtual-host='+$c.rabbitVhost),('--fulfillment.messages.username='+$c.rabbitUser),('--logging.file.name='+(Join-Path $data 'logs/backend-app.log')))
# ArgumentList text must quote paths containing spaces. Values are literal config, not shell commands.
$quoted=$argsList | ForEach-Object {'"'+$_.Replace('"','\"')+'"'}
$backend=Start-Process (Get-Command java).Source -ArgumentList $quoted -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $data 'logs/backend-out.log') -RedirectStandardError (Join-Path $data 'logs/backend-error.log')
$state=[ordered]@{backendPid=$backend.Id;backendPort=$c.backendPort;frontendPid=$null;frontendPort=$c.frontendPort}
$state | ConvertTo-Json | Set-Content (Join-Path $data 'processes.json') -Encoding utf8NoBOM
try {
    $ready=$false;$until=(Get-Date).AddSeconds(110)
    do {try{$login=Invoke-RestMethod ('http://127.0.0.1:'+$c.backendPort+'/admin-api/system/auth/login') -Method Post -Headers @{'tenant-id'='1'} -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}' -TimeoutSec 3;if($login.code -eq 0){$ready=$true;break}}catch{}
        if($backend.HasExited){throw 'Release backend exited; inspect data/logs'}
        Start-Sleep -Milliseconds 500
    }while((Get-Date) -lt $until)
    if(!$ready){throw 'Release backend login timed out'}
    $frontArgs=@(('"'+(Join-Path $PSScriptRoot 'serve.cjs')+'"'),[string]$c.frontendPort,[string]$c.backendPort,('"'+(Join-Path $root 'web')+'"'))
    $front=Start-Process (Get-Command node).Source -ArgumentList $frontArgs -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $data 'logs/frontend-out.log') -RedirectStandardError (Join-Path $data 'logs/frontend-error.log')
    $state.frontendPid=$front.Id;$state | ConvertTo-Json | Set-Content (Join-Path $data 'processes.json') -Encoding utf8NoBOM
    Write-Host ('RELEASE_READY http://127.0.0.1:'+$c.frontendPort)
}catch{if(!$backend.HasExited){Stop-Process -Id $backend.Id};throw}
