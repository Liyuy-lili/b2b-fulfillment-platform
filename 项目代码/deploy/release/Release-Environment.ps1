function Read-ReleaseConfig([string]$Path) {
    $c=Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json
    if($c.database -notmatch '^fulfillment_[a-z0-9_]+$'){throw 'A separate fulfillment_suffix database is required'}
    if($c.dbUser -notmatch '^[A-Za-z0-9_]+$'){throw 'Invalid application database user'}
    foreach($name in @('dbPort','redisPort','rabbitPort','backendPort','frontendPort')){if([int]$c.$name -lt 1024 -or [int]$c.$name -gt 65535){throw "Invalid port: $name"}}
    if($c.backendPort -eq $c.frontendPort){throw 'Application ports must differ'}
    if([int]$c.redisDatabase -lt 1 -or [int]$c.redisDatabase -gt 15){throw 'Use a dedicated Redis DB1-15; DB0 belongs to the main demo'}
    if($c.rabbitVhost -notmatch '^fulfillment_[a-z0-9_]+$'){throw 'Use a separate Broker vhost'}
    if([int]$c.javaHeapMb -lt 256 -or [int]$c.javaHeapMb -gt 4096){throw 'Invalid heap bound'}
    return $c
}
function Set-ReleaseEnvironment($c) {
    $env:DB_NAME=$c.database;$env:DB_HOST=$c.dbHost;$env:DB_PORT=[string]$c.dbPort;$env:DB_USER=$c.dbUser;$env:DB_PASSWORD=$c.dbPassword
    $env:REDIS_HOST=$c.redisHost;$env:REDIS_PORT=[string]$c.redisPort
    # Redisson distinguishes null (no authentication) from an empty AUTH password.
    if([string]::IsNullOrEmpty($c.redisPassword)){Remove-Item Env:SPRING_DATA_REDIS_PASSWORD -ErrorAction SilentlyContinue}else{$env:SPRING_DATA_REDIS_PASSWORD=$c.redisPassword}
    $env:FULFILLMENT_MESSAGES_PASSWORD=$c.rabbitPassword
}
function Test-ReleaseFiles([string]$Root) {
    $manifest=Get-Content -LiteralPath (Join-Path $Root 'manifest.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $prefix=[IO.Path]::GetFullPath($Root)+[IO.Path]::DirectorySeparatorChar
    foreach($file in $manifest.files){
        $path=[IO.Path]::GetFullPath((Join-Path $Root $file.path))
        if(!$path.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Manifest path escapes release'}
        if(!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256){throw ('Release hash mismatch: '+$file.path)}
    }
}
