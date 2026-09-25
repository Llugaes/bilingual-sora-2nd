# Create launch shortcuts only. This script never starts the game or backend.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$entryPath = Join-Path $projectRoot 'update_bootstrap.py'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Missing project Python environment.' }
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcutDirectories = @($projectRoot, [Environment]::GetFolderPath('Desktop')) | Select-Object -Unique
foreach ($shortcutDirectory in $shortcutDirectories) {
    if (-not (Test-Path -LiteralPath $shortcutDirectory -PathType Container)) { continue }
    $shortcutPath = Join-Path $shortcutDirectory 'Sora Bilingual.lnk'
    $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
    if ((Test-Path -LiteralPath $shortcutPath) -and $shortcut.TargetPath -ne $pythonPath) {
        throw "A different shortcut already exists: $shortcutPath"
    }
    $shortcut.TargetPath = $pythonPath
    $shortcut.Arguments = '"' + $entryPath + '" --connect'
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = (Join-Path $projectRoot 'assets\sora-bilingual.ico') + ',0'
    $shortcut.Description = 'Sora bilingual overlay and settings. Connects to an already-running game.'
    $shortcut.Save()
    Write-Output $shortcutPath
}
