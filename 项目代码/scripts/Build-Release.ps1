param([string]$Name=('fulfillment-'+(Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference='Stop'
if($Name -notmatch '^fulfillment-[a-zA-Z0-9-]+$'){throw 'Invalid release name'}
$projectRoot=Split-Path $PSScriptRoot -Parent;$releases=Join-Path $projectRoot '.local/releases';$destination=Join-Path $releases $Name
if(Test-Path -LiteralPath $destination){throw 'Release destination exists; never overwrite a built release'}
$backend=Join-Path $projectRoot 'backend/yudao-server/target/yudao-server.jar';if(!(Test-Path -LiteralPath $backend)){throw 'Build backend first'}
$logs=Join-Path $projectRoot '.local';$pnpm=Join-Path $projectRoot '.local/node-tools/node_modules/.bin/pnpm.cmd'
Push-Location (Join-Path $projectRoot 'frontend')
try {
    & node --max-old-space-size=4096 node_modules/vite/bin/vite.js build --mode release --outDir dist-release *> (Join-Path $logs ($Name+'-frontend-build.log'))
    if($LASTEXITCODE -ne 0){throw 'Release frontend build failed'}
}finally{Pop-Location}
New-Item -ItemType Directory -Path $destination,(Join-Path $destination 'app'),(Join-Path $destination 'web'),(Join-Path $destination 'sql'),(Join-Path $destination 'bin'),(Join-Path $destination 'licenses') -Force | Out-Null
Copy-Item -LiteralPath $backend -Destination (Join-Path $destination 'app/backend.jar')
Copy-Item -Path (Join-Path $projectRoot 'frontend/dist-release/*') -Destination (Join-Path $destination 'web') -Recurse
Copy-Item -Path (Join-Path $projectRoot 'deploy/release/*') -Destination (Join-Path $destination 'bin') -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot 'backend/sql/mysql/ruoyi-vue-pro.sql') -Destination (Join-Path $destination 'sql/000-upstream.sql')
foreach($name in @('010-erp.sql','020-local-baseline.sql')){Copy-Item -LiteralPath (Join-Path $projectRoot ('deploy/sql/'+$name)) -Destination (Join-Path $destination ('sql/'+$name))}
Copy-Item -LiteralPath (Join-Path $projectRoot 'backend/LICENSE') -Destination (Join-Path $destination 'licenses/backend-MIT.txt')
Copy-Item -LiteralPath (Join-Path $projectRoot 'frontend/LICENSE') -Destination (Join-Path $destination 'licenses/frontend-MIT.txt')
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs/baseline.lock.json') -Destination (Join-Path $destination 'baseline.lock.json')
Copy-Item -LiteralPath (Join-Path $projectRoot '../学习资料/06-运行交付与证据/独立交付运行手册.md') -Destination (Join-Path $destination 'README.md')
$files=@(Get-ChildItem -LiteralPath $destination -Recurse -File | Sort-Object FullName | ForEach-Object {[ordered]@{path=[IO.Path]::GetRelativePath($destination,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
[ordered]@{formatVersion=1;builtAt=(Get-Date).ToString('o');name=$Name;backendSha256=(Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash.ToLowerInvariant();files=$files} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $destination 'manifest.json') -Encoding utf8NoBOM
[ordered]@{releaseDirectory=$destination;manifestSha256=(Get-FileHash -LiteralPath (Join-Path $destination 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant();files=$files.Count;backendSha256=(Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logs 'm7-release-build.json') -Encoding utf8NoBOM
Write-Host ('RELEASE_BUILT '+$destination)
