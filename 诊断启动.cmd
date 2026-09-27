@echo off
rem Keep this file ASCII-only: cmd.exe mis-parses UTF-8 batch files containing non-ASCII text.
rem Starts the app with --diagnose: a heartbeat every 2 seconds, plus a full thread stack dump
rem when the UI stops processing events. Log file: tmp\mchanhua.log
chcp 65001 >nul
title mchanhua diagnose
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] venv python not found: %PY%
    pause
    exit /b 1
)

echo Starting mchanhua with diagnostics ...
echo Log file: tmp\mchanhua.log
echo.

"%PY%" -m mchanhua run --diagnose

echo.
echo [mchanhua exited] Check tmp\mchanhua.log for heartbeat lines and stack dumps.
pause
