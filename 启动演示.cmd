@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. Please read docs\README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -m app.launch
if errorlevel 1 pause
