param([string]$GamePath)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (-not $GamePath) { $GamePath = Read-Host 'Dossier du client V Rising (celui contenant VRising.exe)' }
if (-not (Test-Path -LiteralPath (Join-Path $GamePath 'VRising.exe'))) { throw 'VRising.exe introuvable. Choisir le dossier du client.' }
if (-not (Test-Path -LiteralPath (Join-Path $GamePath 'BepInEx\core'))) { throw 'Installer BepInEx pour V Rising et lancer le jeu une fois avant cette installation.' }
if (Get-Process -Name VRising -ErrorAction SilentlyContinue) { throw 'Fermer V Rising avant de copier le mod.' }
$source = Join-Path $root 'release\BepInEx\plugins\VampireCompanion\VampireCompanion.dll'
$destination = Join-Path $GamePath 'BepInEx\plugins\VampireCompanion'
if (-not (Test-Path -LiteralPath $source)) { throw 'DLL absente : recompiler avec scripts\Build.ps1.' }
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$dll = Join-Path $destination 'VampireCompanion.dll'
if (Test-Path -LiteralPath $dll) {
    $backupDir = Join-Path $GamePath 'BepInEx\VampireCompanionBackups'
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Copy-Item -LiteralPath $dll -Destination (Join-Path $backupDir ('VampireCompanion-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dll'))
}
Copy-Item -LiteralPath $source -Destination $dll -Force
Write-Host 'Mod copie. Ajouter ce programme comme serveur MCP STDIO :'
Write-Host (Join-Path $root 'release\mcp\VampireCompanion.Mcp.exe')
Write-Host 'Puis lancer V Rising et ouvrir les coffres et stations a observer.'
