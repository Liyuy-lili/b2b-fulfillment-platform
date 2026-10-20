$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Messaging-Environment.ps1')
& (Join-Path $messagingSbin 'rabbitmq-server.bat')
exit $LASTEXITCODE
