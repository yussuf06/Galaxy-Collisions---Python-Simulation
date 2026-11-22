@echo off
setlocal
cd /d "%~dp0"
if not exist "%USERPROFILE%\.venv\Scripts\python.exe" (
  echo The existing Python environment was not found at %USERPROFILE%\.venv.
  pause
  exit /b 1
)
"%USERPROFILE%\.venv\Scripts\python.exe" "%~dp0main.py" %*
if errorlevel 1 pause
