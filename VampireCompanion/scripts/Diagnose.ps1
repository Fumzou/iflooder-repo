param([string]$GamePath)
$ErrorActionPreference = 'Stop'
$out = Join-Path ([Environment]::GetFolderPath('Desktop')) ('VampireCompanion-Diagnostic-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $out | Out-Null
$snapshot = Join-Path $env:LOCALAPPDATA 'VampireCompanion\snapshot.json'
if (Test-Path -LiteralPath $snapshot) { Copy-Item -LiteralPath $snapshot -Destination $out }
if ($GamePath) {
    foreach ($relative in @('BepInEx\LogOutput.log','BepInEx\config\fr.tristan.vampirecompanion.cfg')) {
        $file = Join-Path $GamePath $relative
        if (Test-Path -LiteralPath $file) { Copy-Item -LiteralPath $file -Destination $out }
    }
}
Write-Host "Diagnostic local : $out"
Write-Host 'Examiner ces fichiers avant de les partager : ils contiennent le nom du personnage et les donnees de la partie.'
