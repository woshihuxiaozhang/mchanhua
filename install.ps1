# Install mchanhua for the current user (no admin needed, no third-party tools).
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'dist\mchanhua'
$target = Join-Path $env:LOCALAPPDATA 'Programs\mchanhua'

if (-not (Test-Path (Join-Path $source 'mchanhua.exe'))) {
    Write-Host '[ERROR] dist\mchanhua\mchanhua.exe not found. Run the build (打包.cmd) first.'
    exit 1
}

Write-Host '[1/4] stopping running mchanhua ...'
Get-Process mchanhua -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

Write-Host "[2/4] copying files to $target ..."
if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
$exe = Join-Path $target 'mchanhua.exe'

Write-Host '[3/4] creating shortcuts ...'
$shell = New-Object -ComObject WScript.Shell
$shortcuts = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\mchanhua.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'mchanhua.lnk')
)
foreach ($path in $shortcuts) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $target
    $lnk.IconLocation = $exe
    $lnk.Description = 'mchanhua screen-translation tool'
    $lnk.Save()
}

Write-Host '[4/4] registering uninstall entry ...'
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\mchanhua'
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name DisplayName -Value 'mchanhua'
Set-ItemProperty -Path $key -Name DisplayVersion -Value '4.0.0'
Set-ItemProperty -Path $key -Name Publisher -Value 'mchanhua'
Set-ItemProperty -Path $key -Name InstallLocation -Value $target
Set-ItemProperty -Path $key -Name DisplayIcon -Value $exe
Set-ItemProperty -Path $key -Name UninstallString -Value ('powershell -NoProfile -ExecutionPolicy Bypass -File "{0}\uninstall.ps1"' -f $PSScriptRoot)

Write-Host ''
Write-Host "[OK] installed to $target"
Write-Host 'Start it from the Start Menu or Desktop shortcut (mchanhua).'
Write-Host 'Config and logs live in %APPDATA%\mchanhua and are kept on uninstall.'
