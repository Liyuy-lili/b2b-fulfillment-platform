param()
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$pnpm=Join-Path $projectRoot '.local/node-tools/node_modules/.bin/pnpm.cmd'
$checks=[System.Collections.Generic.List[object]]::new()
$status='failed'
Push-Location (Join-Path $projectRoot 'frontend')
try {
  $entries=@(
    @{name='eslint';arguments=@('exec','eslint','src/views/erp/reconciliation/index.vue','src/api/erp/reconciliation/index.ts')},
    @{name='stylelint';arguments=@('exec','stylelint','src/views/erp/reconciliation/index.vue')},
    @{name='prettier';arguments=@('exec','prettier','--check','src/views/erp/reconciliation/index.vue','src/api/erp/reconciliation/index.ts')},
    @{name='build';arguments=@('run','build:fulfillment')}
  )
  foreach($entry in $entries) {
    $commandArguments=$entry.arguments
    $log=Join-Path $projectRoot ('.local/m4-reconcile-frontend-'+$entry.name+'.log')
    & $pnpm @commandArguments *> $log
    $code=$LASTEXITCODE
    $checks.Add([ordered]@{name=$entry.name;exit_code=$code;arguments=$commandArguments;log=$log;passed=($code -eq 0)})
    if($code -ne 0) {throw ('Frontend check failed: '+$entry.name)}
  }
  $status='passed'
} finally {
  Pop-Location
  [ordered]@{run_at=(Get-Date).ToString('o');status=$status;checks=$checks} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $projectRoot '../学习资料/10-验收证据/M4.3-frontend.json') -Encoding utf8NoBOM
}
