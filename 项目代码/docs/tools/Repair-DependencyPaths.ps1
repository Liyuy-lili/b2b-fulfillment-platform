$ErrorActionPreference='Stop'
$codeRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$workspaceRoot=Split-Path $codeRoot -Parent
$modules=Join-Path $codeRoot 'frontend/node_modules'
$oldModules=Join-Path $workspaceRoot 'frontend/node_modules'
$links=@(Get-ChildItem -LiteralPath $modules -Recurse -Directory -Attributes ReparsePoint -Force)
$repaired=@()
foreach($link in $links){
    if($link.LinkType -ne 'Junction'){continue}
    $previous=[string]$link.Target
    if(!$previous.StartsWith($oldModules+'\',[StringComparison]::OrdinalIgnoreCase)){continue}
    $next=$modules+$previous.Substring($oldModules.Length)
    $fullNext=[IO.Path]::GetFullPath($next)
    $fullLink=[IO.Path]::GetFullPath($link.FullName)
    if(!$fullLink.StartsWith($modules+'\',[StringComparison]::OrdinalIgnoreCase) -or !$fullNext.StartsWith($modules+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Dependency path escaped intended directory'}
    if(!(Test-Path -LiteralPath $fullNext)){throw ('Missing translated dependency: '+$fullNext)}
    # Delete only the verified junction itself. Never recurse into its target.
    [IO.Directory]::Delete($fullLink,$false)
    New-Item -ItemType Junction -Path $fullLink -Target $fullNext | Out-Null
    $repaired += [ordered]@{path=$fullLink;old=$previous;new=$fullNext}
}
$updated=@()
$shims=@(Get-ChildItem -LiteralPath $modules -Recurse -File -Force | Where-Object {$_.Directory.Name -eq '.bin' -or $_.Name -eq '.modules.yaml'})
foreach($file in $shims){
    $text=[IO.File]::ReadAllText($file.FullName)
    $next=$text.Replace($oldModules,$modules).Replace($oldModules.Replace('\','/'),$modules.Replace('\','/'))
    if($text -ne $next){[IO.File]::WriteAllText($file.FullName,$next,[Text.UTF8Encoding]::new($false));$updated += $file.FullName}
}
$report=[ordered]@{junctions=$repaired.Count;shims_and_metadata=$updated.Count;links=$repaired;updated=$updated}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $codeRoot '.local/dependency-path-repair.json') -Encoding utf8NoBOM
Write-Host ('Dependency path repair: '+$repaired.Count+' junctions; '+$updated.Count+' shims/metadata.')
