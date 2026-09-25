"""Create an optional desktop shortcut without a console or additional packages."""

import base64
import subprocess
from pathlib import Path


def create_desktop_shortcut(root):
    root = Path(root).resolve()
    executable = root / "BilingualSora2nd.exe"
    if not executable.is_file():
        raise RuntimeError("此功能需要 Windows 便携发行包")

    def quoted(value):
        return "'" + str(value).replace("'", "''") + "'"

    script = f"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$path = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Bilingual Sora 2nd.lnk'
$link = $shell.CreateShortcut($path)
if ((Test-Path -LiteralPath $path) -and $link.TargetPath -ne {quoted(executable)}) {{
    throw 'A shortcut with this name already points to another installation.'
}}
$link.TargetPath = {quoted(executable)}
$link.WorkingDirectory = {quoted(root)}
$link.IconLocation = {quoted(executable)} + ',0'
$link.Save()
"""
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(script.encode("utf-16le")).decode("ascii"),
        ],
        check=True,
        capture_output=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
