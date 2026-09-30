@echo off
rem Keep this file ASCII-only (cmd.exe mis-parses UTF-8 batch files with non-ASCII text).
rem Builds the app with PyInstaller, then wraps dist\mchanhua into an installer with Inno Setup.
chcp 65001 >nul
title mchanhua installer build
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if not exist "%PY%" (
    echo [ERROR] venv python not found: %PY%
    pause
    exit /b 1
)
if not exist "%ISCC%" (
    echo [ERROR] Inno Setup not found: %ISCC%
    echo Install it first: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

echo [1/3] running tests ...
"%PY%" -m pytest -q
if errorlevel 1 (
    echo [ERROR] tests failed.
    pause
    exit /b 1
)

echo [2/3] packaging app ...
"%PY%" -m PyInstaller --noconfirm --clean mchanhua.spec
if errorlevel 1 (
    echo [ERROR] packaging failed.
    pause
    exit /b 1
)

echo [3/3] building installer ...
"%ISCC%" installer.iss
if errorlevel 1 (
    echo [ERROR] installer build failed.
    pause
    exit /b 1
)

echo Done. Output: dist\mchanhua-4.0.0-setup.exe
dir /b "dist\mchanhua-4.0.0-setup.exe"
pause
