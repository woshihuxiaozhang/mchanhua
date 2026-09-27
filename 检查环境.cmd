@echo off
rem Keep this file ASCII-only: cmd.exe mis-parses UTF-8 batch files containing
rem non-ASCII text. Chinese messages come from the Python program.
chcp 65001 >nul
title mchanhua probe
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] venv python not found: %PY%
    pause
    exit /b 1
)

"%PY%" -m mchanhua probe
echo.
echo Config file:
"%PY%" -m mchanhua config-path
echo.
pause
