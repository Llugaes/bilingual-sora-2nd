@echo off
cd /d "%~dp0"
py -3.14 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Overlay-Shortcut.ps1"
if errorlevel 1 goto failed
echo Setup complete. Open Sora Bilingual from your desktop.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.14 x64 and check the messages above.
pause
exit /b 1
