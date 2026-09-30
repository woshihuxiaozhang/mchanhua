@echo off
rem Keep this file ASCII-only (cmd.exe mis-parses UTF-8 batch files with non-ASCII text).
rem Build the release zip for GitHub Releases: dist\mchanhua-<version>-win64.zip
chcp 65001 >nul
title mchanhua release zip
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] venv python not found: %PY%
    pause
    exit /b 1
)

echo [1/4] running tests ...
"%PY%" -m pytest -q
if errorlevel 1 (
    echo [ERROR] tests failed, release aborted.
    pause
    exit /b 1
)

echo [2/4] generating icons ...
"%PY%" tools\make_icon.py
"%PY%" tools\make_icons.py

echo [3/4] packaging (this takes a few minutes) ...
"%PY%" -m PyInstaller --noconfirm --clean mchanhua.spec
if errorlevel 1 (
    echo [ERROR] packaging failed.
    pause
    exit /b 1
)
copy /y "assets\HOW-TO-USE.txt" "dist\mchanhua\HOW-TO-USE.txt" >nul

echo [4/4] zipping ...
rem Close a running instance first: it locks files inside _internal and the zip would be incomplete.
taskkill /im mchanhua.exe /f >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make_release_zip.ps1"
if errorlevel 1 (
    echo [ERROR] zip failed.
    pause
    exit /b 1
)

pause
