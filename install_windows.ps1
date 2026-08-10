[CmdletBinding()]
param(
    [switch]$NoStart
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeRoot = Join-Path $Root ".runtime\windows"
$LockPath = Join-Path $Root "windows-runtime.lock.json"
$TranscriptPath = Join-Path $Root "install-windows.log"
$script:TranscriptStarted = $false

Set-Location $Root
$HelpersPath = Join-Path $Root "windows_runtime_helpers.ps1"
if (-not (Test-Path -LiteralPath $HelpersPath -PathType Leaf)) {
    throw "windows_runtime_helpers.ps1 is missing; download the project again"
}
. $HelpersPath

if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
    throw "windows-runtime.lock.json is missing; download the project again"
}
$RuntimeLock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
$PythonRoot = Join-Path $RuntimeRoot ("python-" + [string]$RuntimeLock.artifacts.python.version)
$RuntimePython = Join-Path $PythonRoot ([string]$RuntimeLock.pythonTree.executablePath)
$NativeRoot = Join-Path $RuntimeRoot ("native-" + [string]$RuntimeLock.runtime)

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Stop-InstallerTranscript {
    if ($script:TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
        $script:TranscriptStarted = $false
    }
}

function Get-Artifact([string]$Name) {
    $Artifact = $RuntimeLock.artifacts.$Name
    if (-not $Artifact) { throw "Unknown runtime artifact: $Name" }
    return $Artifact
}

function Get-VerifiedArtifact([string]$Name) {
    $Artifact = Get-Artifact $Name
    $Path = Join-Path $Root ([string]$Artifact.path)
    if (-not (Test-PropExtractFileSha256 $Path ([string]$Artifact.sha256))) {
        throw "Bundled artifact is missing or damaged: $($Artifact.filename). Download the project again."
    }
    Write-Host "Verified bundled artifact: $($Artifact.filename)"
    return $Path
}

function Get-VerifiedPythonPackage([object]$Package) {
    $Path = Join-Path $Root ([string]$Package.path)
    if (-not (Test-PropExtractFileSha256 $Path ([string]$Package.sha256))) {
        throw "Bundled Python package is missing or damaged: $($Package.filename). Download the project again."
    }
    Write-Host "Verified bundled Python package: $($Package.filename)"
    return $Path
}

function Get-WindowsArchitecture {
    $Architecture = $null
    try {
        $Architecture = (Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" -Name PROCESSOR_ARCHITECTURE).PROCESSOR_ARCHITECTURE
    } catch { }
    if (-not $Architecture) { $Architecture = $env:PROCESSOR_ARCHITEW6432 }
    if (-not $Architecture) { $Architecture = $env:PROCESSOR_ARCHITECTURE }
    switch -Regex ([string]$Architecture) {
        "ARM64" { return "arm64" }
        "AMD64" { return "x64" }
        "x86" { return "x86" }
        default { return "unknown" }
    }
}

function Assert-SupportedWindows {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "32-bit Windows is not supported: the pinned OCR runtime is x64"
    }
    $Architecture = Get-WindowsArchitecture
    if ($Architecture -eq "x64") {
        Write-Host "Windows architecture: x64"
        return
    }
    if ($Architecture -eq "arm64") {
        if ([Environment]::OSVersion.Version.Build -lt 22000) {
            throw "ARM64 requires Windows 11 with x64 application emulation"
        }
        Write-Warning "ARM64 detected. The pinned x64 runtime will run through Windows 11 emulation and will be tested before use."
        return
    }
    throw "Unsupported Windows architecture: $Architecture"
}

function Test-PythonRuntime([string]$Path) {
    if (-not (Test-PropExtractPythonTree $Path $RuntimeLock)) { return $false }
    $Python = Join-Path $Path ([string]$RuntimeLock.pythonTree.executablePath)
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { return $false }
    $OldNoBytecode = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = "1"
    try {
        $Probe = & $Python -B -S -c "import openpyxl,struct,sys; from openpyxl import Workbook; Workbook(); print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{struct.calcsize(`"P`")*8}|openpyxl-{openpyxl.__version__}')" 2>$null
        $Expected = "$([string]$RuntimeLock.artifacts.python.version)|64|openpyxl-3.1.5"
        return ($LASTEXITCODE -eq 0) -and (($Probe | Out-String).Trim() -eq $Expected)
    } catch {
        return $false
    } finally {
        $env:PYTHONDONTWRITEBYTECODE = $OldNoBytecode
    }
}

function Publish-RuntimeTree([string]$Staging, [string]$Target) {
    $Backup = $null
    if (Test-Path -LiteralPath $Target) {
        $Backup = "$Target.invalid.$(Get-Date -Format 'yyyyMMdd-HHmmss').$([Guid]::NewGuid().ToString('N'))"
        Move-Item -LiteralPath $Target -Destination $Backup
    }
    try {
        Move-Item -LiteralPath $Staging -Destination $Target
    } catch {
        $PublishError = $_
        if ($Backup -and -not (Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $Backup)) {
            try {
                Move-Item -LiteralPath $Backup -Destination $Target
            } catch {
                Write-Warning "Runtime rollback failed; preserved tree: $Backup"
            }
        }
        throw $PublishError
    }
}

function Install-PythonRuntime {
    if (Test-PythonRuntime $PythonRoot) {
        Write-Host "Pinned portable Python is ready: $PythonRoot"
        return $RuntimePython
    }

    Write-Step "Preparing portable Python 3.12.10 (no installer, no UAC)"
    $PythonArchive = Get-VerifiedArtifact "python"
    $VerifiedPackages = @()
    foreach ($Package in $RuntimeLock.pythonTree.packages) {
        $VerifiedPackages += Get-VerifiedPythonPackage $Package
    }
    $PthTemplate = Join-Path $Root ([string]$RuntimeLock.pythonTree.pthTemplatePath)
    if (-not (Test-Path -LiteralPath $PthTemplate -PathType Leaf)) {
        throw "python312._pth is missing; download the project again"
    }

    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    $Staging = Join-Path $RuntimeRoot ("python-staging-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $Staging -Force | Out-Null
    Expand-Archive -LiteralPath $PythonArchive -DestinationPath $Staging -Force
    $SitePackages = Join-Path $Staging "Lib\site-packages"
    New-Item -ItemType Directory -Path $SitePackages -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($PackagePath in $VerifiedPackages) {
        [IO.Compression.ZipFile]::ExtractToDirectory([string]$PackagePath, $SitePackages)
    }
    Copy-Item -LiteralPath $PthTemplate -Destination (Join-Path $Staging "python312._pth") -Force

    if (-not (Test-PythonRuntime $Staging)) {
        throw "Portable Python integrity or import check failed. Staging kept for diagnostics: $Staging"
    }
    Publish-RuntimeTree $Staging $PythonRoot
    Write-Host "Portable Python verified: $PythonRoot"
    return $RuntimePython
}

function Invoke-NativeProbe([string]$Path, [string[]]$Arguments) {
    try {
        $Output = & $Path @Arguments 2>&1 | Out-String
        return [PSCustomObject]@{ ExitCode = $LASTEXITCODE; Output = $Output }
    } catch {
        return [PSCustomObject]@{ ExitCode = -1; Output = $_.Exception.Message }
    }
}

function Test-NativeRuntime([string]$Path) {
    if (-not (Test-PropExtractNativeTree $Path $RuntimeLock)) { return $false }
    $Tesseract = Get-PropExtractNativeTool $Path "tesseract" $RuntimeLock
    $PdfInfo = Get-PropExtractNativeTool $Path "pdfinfo" $RuntimeLock
    $PdfToPpm = Get-PropExtractNativeTool $Path "pdftoppm" $RuntimeLock
    if (-not $Tesseract -or -not $PdfInfo -or -not $PdfToPpm) { return $false }

    $OldTessdata = $env:TESSDATA_PREFIX
    $env:TESSDATA_PREFIX = Join-Path $Root "rns_import_server\tessdata"
    try {
        $Version = Invoke-NativeProbe $Tesseract.FullName @("--version")
        $Languages = Invoke-NativeProbe $Tesseract.FullName @("--list-langs")
        $Info = Invoke-NativeProbe $PdfInfo.FullName @("-v")
        $Render = Invoke-NativeProbe $PdfToPpm.FullName @("-v")
        return (
            $Version.ExitCode -eq 0 -and $Version.Output -match "tesseract 5\." -and
            $Languages.ExitCode -eq 0 -and $Languages.Output -match "(?m)^rus\s*$" -and
            $Languages.Output -match "(?m)^eng\s*$" -and
            $Info.ExitCode -eq 0 -and $Render.ExitCode -eq 0
        )
    } finally {
        $env:TESSDATA_PREFIX = $OldTessdata
    }
}

function Install-NativeRuntime {
    if (Test-NativeRuntime $NativeRoot) {
        Write-Host "Pinned OCR runtime is ready: $NativeRoot"
        return $NativeRoot
    }

    Write-Step "Preparing portable Tesseract and Poppler (no installer, no UAC)"
    $TesseractArchive = Get-VerifiedArtifact "tesseract"
    $PopplerArchive = Get-VerifiedArtifact "poppler"
    $VcRuntimeCab = Get-VerifiedArtifact "vcruntime"
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    $Staging = Join-Path $RuntimeRoot ("native-staging-" + [Guid]::NewGuid().ToString("N"))
    $PopplerPath = Join-Path $Staging "poppler"
    New-Item -ItemType Directory -Path $Staging -Force | Out-Null
    New-Item -ItemType Directory -Path $PopplerPath -Force | Out-Null

    Expand-Archive -LiteralPath $TesseractArchive -DestinationPath $Staging -Force
    Expand-Archive -LiteralPath $PopplerArchive -DestinationPath $PopplerPath -Force
    $PopplerBin = Join-Path $Staging ([string]$RuntimeLock.nativeTree.popplerBinPath)
    if (-not (Test-Path -LiteralPath (Join-Path $PopplerBin "pdfinfo.exe") -PathType Leaf)) {
        throw "Pinned Poppler archive has an unexpected layout"
    }

    $VcStaging = Join-Path $Staging "vcruntime"
    New-Item -ItemType Directory -Path $VcStaging -Force | Out-Null
    $ExpandExe = Join-Path $env:SystemRoot "System32\expand.exe"
    & $ExpandExe "-F:*" $VcRuntimeCab $VcStaging | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Microsoft VC runtime CAB extraction failed" }
    foreach ($File in Get-ChildItem -LiteralPath $VcStaging -File) {
        $TargetName = $File.Name -replace "_amd64$", ""
        Copy-Item -LiteralPath $File.FullName -Destination (Join-Path $PopplerBin $TargetName) -Force
    }
    Remove-Item -LiteralPath $VcStaging -Recurse -Force

    if (-not (Test-NativeRuntime $Staging)) {
        throw "Portable OCR runtime integrity or smoke check failed. Staging kept for diagnostics: $Staging"
    }
    Publish-RuntimeTree $Staging $NativeRoot
    Write-Host "Portable OCR runtime verified: $NativeRoot"
    return $NativeRoot
}

try {
    try {
        Start-Transcript -LiteralPath $TranscriptPath -Append | Out-Null
        $script:TranscriptStarted = $true
    } catch {
        Write-Warning "Installation log could not be opened: $($_.Exception.Message)"
    }

    Write-Step "Checking Windows platform"
    Assert-SupportedWindows
    Write-Host "WinGet, Microsoft Store, network downloads and administrator rights are not used."

    $Python = Install-PythonRuntime
    $Native = Install-NativeRuntime
    $TesseractDirectory = (Get-PropExtractNativeTool $Native "tesseract" $RuntimeLock).Directory.FullName
    $PopplerDirectory = (Get-PropExtractNativeTool $Native "pdfinfo" $RuntimeLock).Directory.FullName
    $env:Path = "$TesseractDirectory;$PopplerDirectory;$env:Path"
    $env:TESSDATA_PREFIX = Join-Path $Root "rns_import_server\tessdata"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    Write-Step "Checking the complete OCR runtime"
    & $Python -B -S -m rns_import_server.runtime
    if ($LASTEXITCODE -ne 0) { throw "OCR runtime check failed" }

    Write-Host "`nPropExtract is ready." -ForegroundColor Green
    Write-Host "Installation log: $TranscriptPath"
    Stop-InstallerTranscript
    if (-not $NoStart) {
        & (Join-Path $Root "start_windows.cmd")
        if ($LASTEXITCODE -ne 0) { throw "PropExtract automatic start failed with exit code $LASTEXITCODE" }
    }
} catch {
    Write-Host "`nINSTALLATION ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Log: $TranscriptPath"
    throw
} finally {
    Stop-InstallerTranscript
}
