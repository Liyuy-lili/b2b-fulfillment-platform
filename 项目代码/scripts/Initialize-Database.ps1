param(
    [string]$Database = 'fulfillment',
    [string]$MysqlBin = "$env:USERPROFILE\.cache\fulfillment-m0\tools\mysql-8.4.6-winx64\bin",
    [int]$Port = 33306,
    [string]$RootPassword = 'local-root-dev'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if ($Database -notmatch '^fulfillment(?:_[a-z0-9_]+)?$') { throw 'Use a project-specific fulfillment[_suffix] database name.' }
$client = Join-Path $MysqlBin 'mysql.exe'
if (!(Test-Path -LiteralPath $client)) { throw 'Run Bootstrap-Local.ps1 first, or pass -MysqlBin.' }
$oldPassword = $env:MYSQL_PWD
try {
    $env:MYSQL_PWD = $RootPassword
    $clientArgs = @('--no-defaults', '--host=127.0.0.1', "--port=$Port", '--user=root', '--default-character-set=utf8mb4')
    $existing = & $client @clientArgs --batch --skip-column-names -e "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$Database'"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot connect as local project root.' }
    if ($existing) { throw "Database $Database exists. Initialization refuses to overwrite it." }
    & $client @clientArgs -e "CREATE DATABASE $Database CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    if ($LASTEXITCODE -ne 0) { throw 'Create database failed.' }
    # Stream files as UTF-8 through stdin. Never place the upstream DROP statements in an existing DB.
    foreach ($sql in @('backend/sql/mysql/ruoyi-vue-pro.sql', 'deploy/sql/010-erp.sql', 'deploy/sql/020-local-baseline.sql')) {
        $path = Join-Path $root $sql
        $info = [Diagnostics.ProcessStartInfo]::new($client)
        $info.UseShellExecute = $false
        $info.RedirectStandardInput = $true
        $info.StandardInputEncoding = [Text.UTF8Encoding]::new($false)
        foreach ($arg in ($clientArgs + @($Database))) { $info.ArgumentList.Add($arg) }
        $proc = [Diagnostics.Process]::Start($info)
        $proc.StandardInput.Write([IO.File]::ReadAllText($path, [Text.Encoding]::UTF8))
        $proc.StandardInput.Close()
        $proc.WaitForExit()
        if ($proc.ExitCode -ne 0) { throw "SQL failed: $sql. Database retained for diagnosis; no automatic reset." }
        Write-Host "Applied $sql"
    }
    & $client @clientArgs -e "CREATE USER IF NOT EXISTS 'fulfillment'@'127.0.0.1' IDENTIFIED BY 'fulfillment-dev'; GRANT ALL ON $Database.* TO 'fulfillment'@'127.0.0.1';"
    if ($LASTEXITCODE -ne 0) { throw 'Local application user setup failed.' }
    Write-Host "Initialized $Database. Existing databases were not changed."
} finally {
    $env:MYSQL_PWD = $oldPassword
}
