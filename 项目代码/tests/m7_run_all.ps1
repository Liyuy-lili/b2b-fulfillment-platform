param([string[]]$Cases=@('core','expiry','returns','reconcile','message','filefoundation','file'))
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$env:M0_PWSH=(Get-Command pwsh).Source
$redis=Get-ChildItem -LiteralPath (Join-Path $projectRoot '.local/tools') -Recurse -Filter redis-cli.exe | Select-Object -First 1
foreach($case in $Cases){
    if($case -notin @('core','expiry','returns','reconcile','message','filefoundation','file')){throw 'Unknown M7 suite'}
    foreach($port in @(48082,48083,48084)){if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){throw ('Suite port not free: '+$port)}}
    # DB12 is explicitly reserved for disposable M7 regressions; DB0/9/10/11
    # belong to main delivery/performance and must never be flushed here.
    # File core continues the foundation SQL schema, so its Redis sequences
    # must continue too. Fresh-schema suites can reset this disposable DB.
    if($case -ne 'file'){
        & $redis.FullName -h 127.0.0.1 -p 36379 -n 12 FLUSHDB
        if($LASTEXITCODE -ne 0){throw 'M7 test-only Redis reset failed'}
    }
    & C:/veighna_studio/python.exe (Join-Path $PSScriptRoot 'm7_regression.py') $case *> (Join-Path $projectRoot ('.local/m7-regression-'+$case+'.log'))
    if($LASTEXITCODE -ne 0){throw ('M7 suite failed: '+$case)}
    Write-Host ('M7_SUITE_PASSED '+$case)
}
