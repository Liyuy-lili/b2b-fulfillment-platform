param([Parameter(Mandatory)][string]$Config,[Parameter(Mandatory)][string]$MysqlClient,[string]$AdminUser='root')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Release-Environment.ps1')
$root=Split-Path $PSScriptRoot -Parent
Test-ReleaseFiles $root
$c=Read-ReleaseConfig $Config
if(!$env:DB_ADMIN_PASSWORD){throw 'Provide DB_ADMIN_PASSWORD in this process environment'}
if(!(Test-Path -LiteralPath $MysqlClient -PathType Leaf)){throw 'MysqlClient must be an existing mysql CLI'}
$savedPassword=$env:MYSQL_PWD
try {
    $env:MYSQL_PWD=$env:DB_ADMIN_PASSWORD
    $argsList=@('--no-defaults',('--host='+$c.dbHost),('--port='+$c.dbPort),('--user='+$AdminUser),'--default-character-set=utf8mb4')
    $exists=& $MysqlClient @argsList --batch --skip-column-names -e ('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='''+$c.database+'''')
    if($LASTEXITCODE -ne 0){throw 'Cannot connect to the specified MySQL'}
    if($exists){throw 'Database exists; installation refuses overwrite. Use migration/validate separately.'}
    & $MysqlClient @argsList -e ('CREATE DATABASE '+$c.database+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    if($LASTEXITCODE -ne 0){throw 'Create database failed'}
    foreach($name in @('000-upstream.sql','010-erp.sql','020-local-baseline.sql')) {
        $info=[Diagnostics.ProcessStartInfo]::new($MysqlClient);$info.UseShellExecute=$false;$info.RedirectStandardInput=$true;$info.StandardInputEncoding=[Text.UTF8Encoding]::new($false)
        foreach($a in ($argsList+@($c.database))){$info.ArgumentList.Add($a)}
        $p=[Diagnostics.Process]::Start($info);$p.StandardInput.Write([IO.File]::ReadAllText((Join-Path $root ('sql/'+$name)),[Text.Encoding]::UTF8));$p.StandardInput.Close();$p.WaitForExit()
        if($p.ExitCode -ne 0){throw ('Initialization failed; database retained: '+$name)}
    }
    $password=$c.dbPassword.Replace('\','\\').Replace("'","''")
    & $MysqlClient @argsList -e ("CREATE USER IF NOT EXISTS '"+$c.dbUser+"'@'127.0.0.1' IDENTIFIED BY '"+$password+"'; GRANT ALL ON "+$c.database+".* TO '"+$c.dbUser+"'@'127.0.0.1';")
    if($LASTEXITCODE -ne 0){throw 'Application user grant failed'}
    Set-ReleaseEnvironment $c
    foreach($action in @('baseline','migrate','validate')) {
        & java '-Dloader.main=cn.iocoder.yudao.module.fulfillment.framework.FulfillmentMigrationTool' -cp (Join-Path $root 'app/backend.jar') org.springframework.boot.loader.launch.PropertiesLauncher $action
        if($LASTEXITCODE -ne 0){throw ('Migration failed: '+$action)}
    }
    Write-Host ('RELEASE_INSTALL_OK '+$c.database)
} finally {$env:MYSQL_PWD=$savedPassword}
