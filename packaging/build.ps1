# Builds dist\ClaudeBuddy-Setup-<version>.exe  (PyInstaller one-folder app + Inno Setup installer)
# Usage:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 no esta instalado (winget install JRSoftware.InnoSetup --scope user)" }

Write-Host "==> Dependencias"
uv sync
if ($LASTEXITCODE) { throw "uv sync fallo" }

Write-Host "==> Tests"
uv run pytest -q
if ($LASTEXITCODE) { throw "Los tests fallan: no se genera el instalador" }

Write-Host "==> Icono"
uv run python packaging\make_icon.py build\claude-buddy.ico
if ($LASTEXITCODE) { throw "No se pudo generar el icono" }

Write-Host "==> PyInstaller"
uv run pyinstaller --noconfirm --clean packaging\claude-buddy.spec --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE) { throw "PyInstaller fallo" }

$version = (uv run python -c "import claude_buddy; print(claude_buddy.__version__)").Trim()
Write-Host "==> Instalador (version $version)"
& $iscc /Qp "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE) { throw "Inno Setup fallo" }

$setup = Join-Path $root "dist\ClaudeBuddy-Setup-$version.exe"
Write-Host ("Listo: {0}  ({1:N1} MB)" -f $setup, ((Get-Item $setup).Length / 1MB))
