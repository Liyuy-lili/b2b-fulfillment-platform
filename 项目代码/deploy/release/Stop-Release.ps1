param()
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent;$statePath=Join-Path $root 'data/processes.json'
if(!(Test-Path -LiteralPath $statePath)){return}
$state=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
foreach($name in @('frontend','backend')){
    $processId=$state.($name+'Pid');if(!$processId){continue}
    $p=Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
    if(!$p){continue}
    if(!$p.CommandLine -or !$p.CommandLine.Contains($root)){throw 'PID ownership changed; refusing stop'}
    Stop-Process -Id $processId
}
Write-Host 'Release applications stopped; databases, Broker and private files retained.'
