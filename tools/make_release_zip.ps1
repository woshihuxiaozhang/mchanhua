# Zip dist\mchanhua into dist\mchanhua-<version>-win64.zip for GitHub Releases.
# The version comes from mchanhua/__init__.py so the file name can never drift.
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'dist\mchanhua'

if (-not (Test-Path (Join-Path $source 'mchanhua.exe'))) {
    Write-Host '[ERROR] dist\mchanhua\mchanhua.exe not found. Run 打包.cmd first.'
    exit 1
}

$initFile = Join-Path $root 'mchanhua\__init__.py'
$version = (Select-String -Path $initFile -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $version) {
    Write-Host '[ERROR] cannot read __version__ from mchanhua\__init__.py'
    exit 1
}

$target = Join-Path $root "dist\mchanhua-$version-win64.zip"
if (Test-Path $target) { Remove-Item -LiteralPath $target -Force }

Write-Host "zipping $source -> $target"
Compress-Archive -Path (Join-Path $source '*') -DestinationPath $target -CompressionLevel Optimal

$size = [math]::Round((Get-Item $target).Length / 1MB, 1)
Write-Host ''
Write-Host "[OK] $target  ($size MB)"
