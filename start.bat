@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto install
".venv\Scripts\python.exe" -c "import aiohttp, qrcode, vgamepad, pynput, PIL" >nul 2>&1
if not errorlevel 1 goto run

:install
echo [INFO] First launch. Installing required components...
call install.bat
if errorlevel 1 goto failed

:run
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
".venv\Scripts\python.exe" server.py
if errorlevel 1 goto failed
goto finished

:failed
echo.
echo [ERROR] Wi-Fi Gamepad could not start.
echo Read README.md or send a photo of this window.

:finished
echo.
pause
endlocal
