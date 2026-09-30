@echo off
rem Keep this file ASCII-only (cmd.exe mis-parses UTF-8 batch files with non-ASCII text).
rem One-click build: run tests, generate icon, package with PyInstaller into dist\mchanhua.
chcp 65001 >nul
title mchanhua build
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
    echo [ERROR] tests failed, build aborted.
    pause
    exit /b 1
)

echo [2/4] generating icon ...
"%PY%" tools\make_icon.py
"%PY%" tools\make_icons.py

echo [3/4] packaging (this takes a few minutes) ...
"%PY%" -m PyInstaller --noconfirm --clean mchanhua.spec
if errorlevel 1 (
    echo [ERROR] packaging failed.
    pause
    exit /b 1
)

rem ship the how-to-use note next to the exe (ASCII filename, UTF-8 content)
copy /y "assets\HOW-TO-USE.txt" "dist\mchanhua\HOW-TO-USE.txt" >nul

echo [4/4] done. Output: dist\mchanhua\mchanhua.exe
dir /s /-c "dist\mchanhua\mchanhua.exe" | findstr mchanhua.exe
pause
