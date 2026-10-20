param()
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$runtimeRoot=Join-Path $env:USERPROFILE '.cache/fulfillment-m0'
$archives=@(
 @{name='otp_win64_27.3.4.17.zip'; url='https://github.com/erlang/otp/releases/download/OTP-27.3.4.17/otp_win64_27.3.4.17.zip'; hash='d0c9f030909eed5484a803f8a9e9e3a2d2275d3e531a4e0891cb61fd1f88697f'; directory='erlang-27.3.4.17'},
 @{name='rabbitmq-server-windows-4.2.5.zip'; url='https://github.com/rabbitmq/rabbitmq-server/releases/download/v4.2.5/rabbitmq-server-windows-4.2.5.zip'; hash='04a503d07c98891f2623f4ee2aeaee2f740e19c0446393078e65b0696e739a98'; directory='rabbitmq-4.2.5'}
)
foreach($archive in $archives){
 $file=Join-Path $runtimeRoot ('tools/'+$archive.name)
 if(!(Test-Path -LiteralPath $file)){Invoke-WebRequest -Uri $archive.url -OutFile $file}
 if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archive.hash){throw ('Archive hash mismatch: '+$archive.name)}
 $destination=Join-Path $runtimeRoot ('tools/'+$archive.directory)
 if(!(Test-Path -LiteralPath $destination)){Expand-Archive -LiteralPath $file -DestinationPath $destination}
}
& (Join-Path $runtimeRoot 'tools/erlang-27.3.4.17/bin/erl.exe') -noshell -eval 'io:format("OTP ~s~n", [erlang:system_info(otp_release)]),halt().'
if($LASTEXITCODE -ne 0){throw 'Portable Erlang did not run; inspect the official package INSTALL.txt'}
Write-Host 'Project-local Erlang/RabbitMQ archives verified; no Windows service installed.'
