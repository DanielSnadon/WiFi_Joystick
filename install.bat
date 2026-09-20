@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto dependencies

set "PY_CMD="
py -3.11 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3.11"
if defined PY_CMD goto create_venv
py -3.12 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3.12"
if defined PY_CMD goto create_venv
py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
if defined PY_CMD goto create_venv
python -c "import sys" >nul 2>&1 && set "PY_CMD=python"
if defined PY_CMD goto create_venv
goto no_python

:create_venv
echo [INFO] Creating the Python environment...
%PY_CMD% -m venv .venv
if errorlevel 1 goto failed

:dependencies
echo [INFO] Installing Python packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo [OK] Components installed successfully.
echo If ViGEmBus is not installed, run install-driver.bat next.
endlocal
exit /b 0

:no_python
echo.
echo [ERROR] Python was not found.
echo Install Python 3.11 or 3.12 and enable "Add Python to PATH".
echo Download page: https://www.python.org/downloads/windows/
goto failed_exit

:failed
echo.
echo [ERROR] Installation failed. Send a photo of this window.

:failed_exit
pause
endlocal
exit /b 1
