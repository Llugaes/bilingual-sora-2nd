@echo off
cd /d "%~dp0"
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0update_bootstrap.py" --expanded
