$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (!(Test-Path .\summa_cut)) {
    Write-Host 'Uruchom skrypt w katalogu projektu summa-cut.' -ForegroundColor Red
    exit 1
}

if (!(Test-Path .\.venv\Scripts\python.exe)) {
    py -3.12 -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

if (Test-Path .\build) { Remove-Item .\build -Recurse -Force }
if (Test-Path .\dist\summa-cut) { Remove-Item .\dist\summa-cut -Recurse -Force }
if (Test-Path .\summa-cut.spec) { Remove-Item .\summa-cut.spec -Force }

pyinstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name "summa-cut" `
  --add-data "settings.json;." `
  app.py

Write-Host ''
Write-Host 'Build zakończony.' -ForegroundColor Green
Write-Host 'Gotowy program:' -ForegroundColor Green
Write-Host (Join-Path $root 'dist\summa-cut\summa-cut.exe')
