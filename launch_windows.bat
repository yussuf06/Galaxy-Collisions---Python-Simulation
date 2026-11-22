@echo off
setlocal
cd /d "%~dp0"
set "PY_CMD="
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3.12"
if defined PY_CMD goto python_found
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3.11"
if defined PY_CMD goto python_found
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if defined PY_CMD goto python_found
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if defined PY_CMD goto python_found
echo Install Python 3.11 or 3.12 from python.org, then run this launcher again.
pause
exit /b 1
:python_found
%PY_CMD% -c "import sys; assert (3,10) <= sys.version_info[:2] < (3,14), 'Use Python 3.10 to 3.13. Python 3.11 or 3.12 is recommended.'"
if errorlevel 1 goto failed
if exist ".venv\Scripts\python.exe" goto dependencies
%PY_CMD% -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -c "import numpy; import PySide6.QtWidgets" >nul 2>&1
if not errorlevel 1 goto accelerator
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
:accelerator
if exist ".venv\.numba_attempted" goto launch
".venv\Scripts\python.exe" -c "import numba" >nul 2>&1
if not errorlevel 1 goto accelerator_done
echo Trying the optional Numba accelerator. NumPy is the fallback.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check numba
if errorlevel 1 echo Optional accelerator unavailable. Continuing with NumPy.
:accelerator_done
type nul > ".venv\.numba_attempted"
:launch
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Setup or launch failed. Read the error above and README.md.
pause
exit /b 1
