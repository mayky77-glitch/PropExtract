$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Install-WingetPackage([string]$Id) {
    winget list --exact --id $Id --accept-source-agreements | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installed: $Id"
        return
    }
    Write-Host "Installing: $Id"
    winget install --exact --id $Id --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget failed: $Id" }
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget is missing. Install Microsoft App Installer, then run install_windows.cmd again."
}

Install-WingetPackage "Python.Python.3.12"
Install-WingetPackage "tesseract-ocr.tesseract"
Install-WingetPackage "oschwartz10612.Poppler"

$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$TesseractDirectory = Join-Path $env:ProgramFiles "Tesseract-OCR"
if ((Test-Path (Join-Path $TesseractDirectory "tesseract.exe")) -and -not (Get-Command tesseract.exe -ErrorAction SilentlyContinue)) {
    $env:Path += ";$TesseractDirectory"
}
$Python = Get-Command py.exe -ErrorAction SilentlyContinue
if ($Python) {
    & $Python.Source -3.12 -m venv .venv
} else {
    $Python = Get-Command python.exe -ErrorAction Stop
    & $Python.Source -m venv .venv
}

& "$Root\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "$Root\requirements-rns-import.txt"
if ($LASTEXITCODE -ne 0) { throw "Python dependencies installation failed" }

& "$Root\.venv\Scripts\python.exe" -m rns_import_server.runtime
if ($LASTEXITCODE -ne 0) { throw "OCR runtime check failed" }

Write-Host "PropExtract is ready. Starting local server..."
& "$Root\start_windows.cmd"
