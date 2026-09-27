# Remove the per-user install created by install.ps1. Keeps %APPDATA%\mchanhua (config/logs).
$ErrorActionPreference = 'Continue'
$target = Join-Path $env:LOCALAPPDATA 'Programs\mchanhua'

Get-Process mchanhua -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\mchanhua.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'mchanhua.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\mchanhua' -Recurse -Force -ErrorAction SilentlyContinue

Write-Host '[OK] mchanhua uninstalled. Your config/logs in %APPDATA%\mchanhua were kept.'
