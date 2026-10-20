param([ValidateSet('baseline','migrate','validate')][string]$Action='validate', [string]$Database='fulfillment')
$ErrorActionPreference='Stop'
if ($Database -notmatch '^fulfillment(?:_[A-Za-z0-9_]+)?$') { throw 'Only project databases are allowed' }
$projectRoot=Split-Path $PSScriptRoot -Parent
$jar=Join-Path $projectRoot 'backend/yudao-server/target/yudao-server.jar'
if (-not (Test-Path -LiteralPath $jar)) { throw 'Build backend first' }
$oldDatabase=$env:DB_NAME
try {
  $env:DB_NAME=$Database
  & java '-Dloader.main=cn.iocoder.yudao.module.fulfillment.framework.FulfillmentMigrationTool' -cp $jar org.springframework.boot.loader.launch.PropertiesLauncher $Action
  if ($LASTEXITCODE -ne 0) { throw "Migration failed: $Action $Database" }
} finally {
  $env:DB_NAME=$oldDatabase
}
