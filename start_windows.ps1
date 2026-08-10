[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$CheckOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$HelpersPath = Join-Path $Root "windows_runtime_helpers.ps1"
$LockPath = Join-Path $Root "windows-runtime.lock.json"
if (-not (Test-Path -LiteralPath $HelpersPath -PathType Leaf)) {
    throw "windows_runtime_helpers.ps1 is missing; download the project again"
}
if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
    throw "windows-runtime.lock.json is missing; download the project again"
}
. $HelpersPath

$RuntimeLock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
$RuntimeRoot = Join-Path $Root ".runtime\windows"
$PythonRoot = Join-Path $RuntimeRoot ("python-" + [string]$RuntimeLock.artifacts.python.version)
$RuntimePython = Join-Path $PythonRoot ([string]$RuntimeLock.pythonTree.executablePath)
$NativeRoot = Join-Path $RuntimeRoot ("native-" + [string]$RuntimeLock.runtime)

if (-not (Test-PropExtractPythonTree $PythonRoot $RuntimeLock)) {
    throw "Portable Python is missing or damaged; run install_windows.cmd again"
}
if (-not (Test-PropExtractNativeTree $NativeRoot $RuntimeLock)) {
    throw "Portable OCR runtime is missing or damaged; run install_windows.cmd again"
}

$Tesseract = Get-PropExtractNativeTool $NativeRoot "tesseract" $RuntimeLock
$PdfInfo = Get-PropExtractNativeTool $NativeRoot "pdfinfo" $RuntimeLock
$PdfToPpm = Get-PropExtractNativeTool $NativeRoot "pdftoppm" $RuntimeLock
if (
    -not (Test-Path -LiteralPath $RuntimePython -PathType Leaf) -or
    -not $Tesseract -or
    -not $PdfInfo -or
    -not $PdfToPpm
) {
    throw "Portable runtime has an unexpected layout; run install_windows.cmd again"
}

$env:Path = "$($Tesseract.Directory.FullName);$($PdfInfo.Directory.FullName);$env:Path"
$env:TESSDATA_PREFIX = Join-Path $Root "rns_import_server\tessdata"
$env:PYTHONDONTWRITEBYTECODE = "1"

$Probe = & $RuntimePython -B -S -c "import openpyxl,sys; from openpyxl import Workbook; Workbook(); print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{64 if sys.maxsize > 2**32 else 32}|openpyxl-{openpyxl.__version__}')" 2>$null
$Expected = "$([string]$RuntimeLock.artifacts.python.version)|64|openpyxl-3.1.5"
$Actual = ($Probe | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $Actual -ne $Expected) {
    throw "Portable Python import check failed; run install_windows.cmd again"
}

& $RuntimePython -B -S -m rns_import_server.runtime
if ($LASTEXITCODE -ne 0) {
    throw "OCR runtime check failed; run install_windows.cmd again"
}
if ($CheckOnly) { exit 0 }

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:8775"
}
& $RuntimePython -B -S -m rns_import_server.app serve --host 127.0.0.1 --port 8775
exit $LASTEXITCODE
