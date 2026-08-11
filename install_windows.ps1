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
    throw "Отсутствует windows_runtime_helpers.ps1; скачайте проект заново."
}
. $HelpersPath

if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
    throw "Отсутствует windows-runtime.lock.json; скачайте проект заново."
}
try {
    $RuntimeLock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    throw "Не удалось прочитать windows-runtime.lock.json; скачайте проект заново."
}
$PythonRoot = Join-Path $RuntimeRoot ("python-" + [string]$RuntimeLock.artifacts.python.version)
$RuntimePython = Join-Path $PythonRoot ([string]$RuntimeLock.pythonTree.executablePath)
$NativeRoot = Join-Path $RuntimeRoot ("native-" + [string]$RuntimeLock.runtime)
$script:InstallerMutex = $null
$script:InstallerMutexHeld = $false

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
    if (-not $Artifact) { throw "Неизвестный компонент runtime: $Name" }
    return $Artifact
}

function Get-VerifiedArtifact([string]$Name) {
    $Artifact = Get-Artifact $Name
    $Path = Join-Path $Root ([string]$Artifact.path)
    if (-not (Test-PropExtractFileSha256 $Path ([string]$Artifact.sha256))) {
        throw "Встроенный компонент отсутствует или повреждён: $($Artifact.filename). Скачайте проект заново."
    }
    Write-Host "Проверен встроенный компонент: $($Artifact.filename)"
    return $Path
}

function Get-VerifiedPythonPackage([object]$Package) {
    $Path = Join-Path $Root ([string]$Package.path)
    if (-not (Test-PropExtractFileSha256 $Path ([string]$Package.sha256))) {
        throw "Встроенный пакет Python отсутствует или повреждён: $($Package.filename). Скачайте проект заново."
    }
    Write-Host "Проверен встроенный пакет Python: $($Package.filename)"
    return $Path
}

function Get-WindowsArchitecture {
    $Architecture = $null
    try {
        $Architecture = (Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" -Name PROCESSOR_ARCHITECTURE).PROCESSOR_ARCHITECTURE
    } catch { }
    if (-not $Architecture) {
        $Architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITEW6432", "Process")
    }
    if (-not $Architecture) {
        $Architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITECTURE", "Process")
    }
    switch -Regex ([string]$Architecture) {
        "ARM64" { return "arm64" }
        "AMD64" { return "x64" }
        "x86" { return "x86" }
        default { return "unknown" }
    }
}

function Assert-SupportedWindows {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "32-разрядная Windows не поддерживается: закреплённый OCR runtime предназначен для x64."
    }
    $Architecture = Get-WindowsArchitecture
    if ($Architecture -eq "x64") {
        Write-Host "Архитектура Windows: x64"
        return
    }
    if ($Architecture -eq "arm64") {
        if ([Environment]::OSVersion.Version.Build -lt 22000) {
            throw "Для ARM64 требуется Windows 11 с эмуляцией приложений x64."
        }
        Write-Warning "Обнаружена ARM64. Закреплённый runtime x64 будет работать через эмуляцию Windows 11 и будет проверен перед использованием."
        return
    }
    throw "Неподдерживаемая архитектура Windows: $Architecture"
}

function Test-PythonRuntime([string]$Path) {
    if (-not (Test-PropExtractPythonTree $Path $RuntimeLock)) { return $false }
    $Python = Join-Path $Path ([string]$RuntimeLock.pythonTree.executablePath)
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { return $false }
    $OldNoBytecode = [Environment]::GetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "Process")
    $OldErrorActionPreference = $ErrorActionPreference
    [Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "1", "Process")
    $ErrorActionPreference = "Continue"
    try {
        $Probe = & $Python -B -S -c "import openpyxl,sys; from openpyxl import Workbook; Workbook(); print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{64 if sys.maxsize > 2**32 else 32}|openpyxl-{openpyxl.__version__}')" 2>&1
        $ProbeExitCode = $LASTEXITCODE
        $Expected = "$([string]$RuntimeLock.artifacts.python.version)|64|openpyxl-3.1.5"
        $ProbeText = ($Probe | Out-String).Trim()
        if (($ProbeExitCode -eq 0) -and ($ProbeText -eq $Expected)) { return $true }
        $PathProbe = & $Python -B -S -c "import sys; print('|'.join(sys.path))" 2>&1 | Out-String
        Write-Warning "Проверка portable Python не пройдена (код $ProbeExitCode). Вывод: $ProbeText. sys.path: $($PathProbe.Trim())"
        return $false
    } catch {
        Write-Warning "Не удалось запустить проверку portable Python: $($_.Exception.Message)"
        return $false
    } finally {
        $ErrorActionPreference = $OldErrorActionPreference
        [Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", $OldNoBytecode, "Process")
    }
}

function Publish-RuntimeTree([string]$Staging, [string]$Target, [scriptblock]$TargetIsVerified) {
    $Backup = $null
    $ReplacementPublished = $false
    if (Test-Path -LiteralPath $Target) {
        $Backup = "$Target.invalid.$(Get-Date -Format 'yyyyMMdd-HHmmss').$([Guid]::NewGuid().ToString('N'))"
        Move-Item -LiteralPath $Target -Destination $Backup
    }
    try {
        Move-Item -LiteralPath $Staging -Destination $Target
        $ReplacementPublished = $true
        if (-not (& $TargetIsVerified $Target)) {
            throw "Проверка опубликованного runtime не пройдена."
        }
    } catch {
        $PublishError = $_
        if ($Backup -and (Test-Path -LiteralPath $Backup)) {
            try {
                if ($ReplacementPublished -and (Test-Path -LiteralPath $Target)) {
                    $Failed = "$Staging.publish-failed.$([Guid]::NewGuid().ToString('N'))"
                    Move-Item -LiteralPath $Target -Destination $Failed
                }
                if (-not (Test-Path -LiteralPath $Target)) {
                    Move-Item -LiteralPath $Backup -Destination $Target
                }
            } catch {
                Write-Warning "Откат runtime не выполнен; сохранено дерево: $Backup"
            }
        }
        throw $PublishError
    }
}

function Install-PythonRuntime {
    if (Test-PythonRuntime $PythonRoot) {
        Write-Host "Закреплённый portable Python готов: $PythonRoot"
        return $RuntimePython
    }

    Write-Step "Подготовка portable Python 3.12.10 (без установщика и UAC)"
    $PythonArchive = Get-VerifiedArtifact "python"
    $VerifiedPackages = @()
    foreach ($Package in $RuntimeLock.pythonTree.packages) {
        $VerifiedPackages += Get-VerifiedPythonPackage $Package
    }
    $PthTemplate = Join-Path $Root ([string]$RuntimeLock.pythonTree.pthTemplatePath)
    if (-not (Test-Path -LiteralPath $PthTemplate -PathType Leaf)) {
        throw "Отсутствует python312._pth; скачайте проект заново."
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
        throw "Проверка целостности или импорта portable Python не пройдена. Временное дерево сохранено для диагностики: $Staging"
    }
    Publish-RuntimeTree $Staging $PythonRoot { param($Path) Test-PythonRuntime $Path }
    Remove-PropExtractStaleRuntimeBackups $PythonRoot { param($Path) Test-PythonRuntime $Path }
    Write-Host "Portable Python проверен: $PythonRoot"
    return $RuntimePython
}

function Invoke-NativeProbe([string]$Path, [string[]]$Arguments) {
    $OldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Output = & $Path @Arguments 2>&1 | Out-String
        return [PSCustomObject]@{ ExitCode = $LASTEXITCODE; Output = $Output }
    } catch {
        return [PSCustomObject]@{ ExitCode = -1; Output = $_.Exception.Message }
    } finally {
        $ErrorActionPreference = $OldErrorActionPreference
    }
}

function Test-NativeRuntime([string]$Path) {
    if (-not (Test-PropExtractNativeTree $Path $RuntimeLock)) {
        if (Test-Path -LiteralPath $Path -PathType Container) {
            $ActualDigest = Get-PropExtractDirectoryDigest $Path
            Write-Warning "Дерево portable OCR не соответствует ожидаемому: файлов=$($ActualDigest.Files), sha256=$($ActualDigest.Sha256)"
        }
        return $false
    }
    $Tesseract = Get-PropExtractNativeTool $Path "tesseract" $RuntimeLock
    $PdfInfo = Get-PropExtractNativeTool $Path "pdfinfo" $RuntimeLock
    $PdfToPpm = Get-PropExtractNativeTool $Path "pdftoppm" $RuntimeLock
    if (-not $Tesseract -or -not $PdfInfo -or -not $PdfToPpm) { return $false }

    $OldTessdata = [Environment]::GetEnvironmentVariable("TESSDATA_PREFIX", "Process")
    [Environment]::SetEnvironmentVariable(
        "TESSDATA_PREFIX",
        "rns_import_server\tessdata",
        "Process"
    )
    try {
        $Version = Invoke-NativeProbe $Tesseract.FullName @("--version")
        $Languages = Invoke-NativeProbe $Tesseract.FullName @("--list-langs")
        $Info = Invoke-NativeProbe $PdfInfo.FullName @("-v")
        $Render = Invoke-NativeProbe $PdfToPpm.FullName @("-v")
        $Ready = (
            $Version.ExitCode -eq 0 -and $Version.Output -match "(?i)tesseract v?5\." -and
            $Languages.ExitCode -eq 0 -and $Languages.Output -match "(?m)^rus\s*$" -and
            $Languages.Output -match "(?m)^eng\s*$" -and
            $Info.ExitCode -eq 0 -and $Render.ExitCode -eq 0
        )
        if (-not $Ready) {
            Write-Warning (
                "Проверка portable OCR не пройдена. " +
                "tesseract(exit=$($Version.ExitCode)): $($Version.Output.Trim()); " +
                "languages(exit=$($Languages.ExitCode)): $($Languages.Output.Trim()); " +
                "pdfinfo(exit=$($Info.ExitCode)): $($Info.Output.Trim()); " +
                "pdftoppm(exit=$($Render.ExitCode)): $($Render.Output.Trim())"
            )
        }
        return $Ready
    } finally {
        [Environment]::SetEnvironmentVariable("TESSDATA_PREFIX", $OldTessdata, "Process")
    }
}

function Install-NativeRuntime {
    if (Test-NativeRuntime $NativeRoot) {
        Write-Host "Закреплённый OCR runtime готов: $NativeRoot"
        return $NativeRoot
    }

    Write-Step "Подготовка portable Tesseract и Poppler (без установщика и UAC)"
    $TesseractArchive = Get-VerifiedArtifact "tesseract"
    $PopplerArchive = Get-VerifiedArtifact "poppler"
    $VcRuntimeArchive = Get-VerifiedArtifact "vcruntime"
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    $Staging = Join-Path $RuntimeRoot ("native-staging-" + [Guid]::NewGuid().ToString("N"))
    $PopplerPath = Join-Path $Staging "poppler"
    New-Item -ItemType Directory -Path $Staging -Force | Out-Null
    New-Item -ItemType Directory -Path $PopplerPath -Force | Out-Null

    Expand-Archive -LiteralPath $TesseractArchive -DestinationPath $Staging -Force
    Expand-Archive -LiteralPath $PopplerArchive -DestinationPath $PopplerPath -Force
    $PopplerBin = Join-Path $Staging ([string]$RuntimeLock.nativeTree.popplerBinPath)
    if (-not (Test-Path -LiteralPath (Join-Path $PopplerBin "pdfinfo.exe") -PathType Leaf)) {
        throw "Закреплённый архив Poppler имеет непредвиденную структуру."
    }

    try {
        Expand-Archive -LiteralPath $VcRuntimeArchive -DestinationPath $PopplerBin -Force
    } catch {
        throw [InvalidOperationException]::new("Не удалось распаковать встроенный архив Microsoft VC runtime.", $_.Exception)
    }

    if (-not (Test-NativeRuntime $Staging)) {
        throw "Проверка целостности или работоспособности portable OCR runtime не пройдена. Временное дерево сохранено для диагностики: $Staging"
    }
    Publish-RuntimeTree $Staging $NativeRoot { param($Path) Test-NativeRuntime $Path }
    Remove-PropExtractStaleRuntimeBackups $NativeRoot { param($Path) Test-NativeRuntime $Path }
    Write-Host "Portable OCR runtime проверен: $NativeRoot"
    return $NativeRoot
}

try {
    $script:InstallerMutex = Get-PropExtractInstallerMutex $Root
    $script:InstallerMutexHeld = Enter-PropExtractInstallerMutex $script:InstallerMutex

    try {
        Start-Transcript -LiteralPath $TranscriptPath -Append | Out-Null
        $script:TranscriptStarted = $true
    } catch {
        Write-Warning "Не удалось открыть журнал установки."
    }

    Assert-PropExtractInstallerPreflight $Root $RuntimeRoot $PythonRoot $NativeRoot $RuntimeLock

    Write-Step "Проверка платформы Windows"
    Assert-SupportedWindows
    Write-Host "WinGet, Microsoft Store, network downloads и права администратора не используются."

    $Python = Install-PythonRuntime
    $Native = Install-NativeRuntime
    $TesseractDirectory = (Get-PropExtractNativeTool $Native "tesseract" $RuntimeLock).Directory.FullName
    $PopplerDirectory = (Get-PropExtractNativeTool $Native "pdfinfo" $RuntimeLock).Directory.FullName
    $env:Path = "$TesseractDirectory;$PopplerDirectory;$env:Path"
    $env:TESSDATA_PREFIX = "rns_import_server\tessdata"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    Write-Step "Проверка полного OCR runtime"
    & $Python -B -S -m rns_import_server.runtime
    if ($LASTEXITCODE -ne 0) { throw "Проверка OCR runtime завершилась с ошибкой." }

    Write-Host "`nPropExtract готов к работе." -ForegroundColor Green
    Write-Host "Журнал установки: $TranscriptPath"
    Stop-InstallerTranscript
    if (-not $NoStart) {
        & (Join-Path $Root "start_windows.cmd")
        if ($LASTEXITCODE -ne 0) { throw "Автоматический запуск PropExtract завершился с кодом $LASTEXITCODE." }
    }
} catch {
    Write-Host "`nОШИБКА УСТАНОВКИ: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Журнал: $TranscriptPath"
    throw
} finally {
    Stop-InstallerTranscript
    if ($script:InstallerMutex) {
        if ($script:InstallerMutexHeld) {
            try { $script:InstallerMutex.ReleaseMutex() } catch { }
        }
        $script:InstallerMutex.Dispose()
        $script:InstallerMutex = $null
        $script:InstallerMutexHeld = $false
    }
}
