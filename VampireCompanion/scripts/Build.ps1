$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    dotnet build src/Mod/VampireCompanion.csproj -c Release
    if ($LASTEXITCODE -ne 0) { throw 'La compilation du mod a echoue.' }
    dotnet publish src/Bridge/VampireCompanion.Mcp.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o release/mcp
    if ($LASTEXITCODE -ne 0) { throw 'La compilation de la passerelle a echoue.' }
    New-Item -ItemType Directory -Path release/BepInEx/plugins/VampireCompanion -Force | Out-Null
    Copy-Item src/Mod/bin/Release/net6.0/VampireCompanion.dll release/BepInEx/plugins/VampireCompanion/ -Force
} finally { Pop-Location }
