@echo off
rem Keep this file ASCII-only (cmd.exe mis-parses UTF-8 batch files with non-ASCII text).
rem Installs mchanhua for the current user: copy to %LOCALAPPDATA%\Programs, create
rem Start Menu + Desktop shortcuts, register an uninstall entry. No admin required.
chcp 65001 >nul
title mchanhua install
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
