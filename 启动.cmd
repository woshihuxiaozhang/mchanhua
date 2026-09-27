@echo off
rem NOTE: keep this file ASCII-only. A UTF-8 batch file with non-ASCII text gets
rem mis-parsed by cmd.exe (it reads the file with the OEM code page). All Chinese
rem messages come from the Python program instead.
chcp 65001 >nul
title mchanhua
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] venv python not found: %PY%
    echo.
    echo Create it first:
    echo     D:\Tools\Miniconda3\python.exe -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Starting mchanhua ...
echo Hotkeys: Ctrl+Alt translate saved region / Alt+/ pick and translate / Alt+m fullscreen
echo Close this window to quit.
echo Log file: tmp\mchanhua.log
echo.

"%PY%" -m mchanhua run

echo.
echo [mchanhua exited] If this was unexpected, the reason is printed above.
pause
