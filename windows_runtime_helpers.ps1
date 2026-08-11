Set-StrictMode -Version 2.0

function Get-PropExtractInstallerMutex([string]$ProjectRoot) {
    $ResolvedRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd("\")
    $Sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $Bytes = [Text.Encoding]::UTF8.GetBytes($ResolvedRoot.ToLowerInvariant())
        $Hash = ([BitConverter]::ToString($Sha256.ComputeHash($Bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $Sha256.Dispose()
    }

    $CreatedNew = $false
    try {
        return New-Object System.Threading.Mutex($false, ("Local\PropExtractInstaller-" + $Hash), [ref]$CreatedNew)
    } catch {
        throw "Не удалось создать блокировку установки для этой папки проекта."
    }
}

function Enter-PropExtractInstallerMutex([System.Threading.Mutex]$Mutex) {
    try {
        if ($Mutex.WaitOne(0)) { return $true }
    } catch [System.Threading.AbandonedMutexException] {
        Write-Warning "Предыдущая установка была аварийно прервана; блокировка восстановлена."
        return $true
    }
    throw "Установка уже выполняется для этой папки проекта. Дождитесь её завершения и повторите попытку."
}

function Test-PropExtractPathIsInside([string]$Parent, [string]$Child) {
    $ParentFull = [IO.Path]::GetFullPath($Parent).TrimEnd("\")
    $ChildFull = [IO.Path]::GetFullPath($Child)
    return (
        $ChildFull.Equals($ParentFull, [StringComparison]::OrdinalIgnoreCase) -or
        $ChildFull.StartsWith(($ParentFull + "\"), [StringComparison]::OrdinalIgnoreCase)
    )
}

function Test-PropExtractTreeContainsReparsePoint([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $Pending = New-Object 'System.Collections.Generic.Stack[string]'
    $Pending.Push([IO.Path]::GetFullPath($Path))
    while ($Pending.Count -gt 0) {
        $Current = Get-Item -LiteralPath $Pending.Pop() -Force -ErrorAction Stop
        if (($Current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            return $true
        }
        if (-not $Current.PSIsContainer) { continue }
        foreach ($Child in @(Get-ChildItem -LiteralPath $Current.FullName -Force -ErrorAction Stop)) {
            if (($Child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                return $true
            }
            if ($Child.PSIsContainer) { $Pending.Push($Child.FullName) }
        }
    }
    return $false
}

function Assert-PropExtractWritableDirectory([string]$Path, [string]$Label) {
    $Probe = Join-Path $Path (".propextract-write-probe-" + [Guid]::NewGuid().ToString("N"))
    $ProbeStream = $null
    try {
        $ProbeStream = [IO.File]::Open(
            $Probe,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::None
        )
        $ProbeStream.Dispose()
        $ProbeStream = $null
    } catch {
        throw "Нет прав на запись в $Label. Переместите проект в доступную папку и повторите установку."
    } finally {
        if ($ProbeStream) { $ProbeStream.Dispose() }
        if (Test-Path -LiteralPath $Probe -PathType Leaf) {
            Remove-Item -LiteralPath $Probe -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-PropExtractFreeBytes([string]$Path) {
    $Item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if (-not $Item.PSDrive -or $null -eq $Item.PSDrive.Free) {
        throw "Не удалось определить свободное место для папки проекта."
    }
    return [int64]$Item.PSDrive.Free
}

function Get-PropExtractArchiveMetadata([string]$Path, [string]$DestinationRoot = $null) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Не найден архив, необходимый для расчёта свободного места: $Path"
    }
    $Archive = $null
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $Archive = [IO.Compression.ZipFile]::OpenRead($Path)
        [int64]$Total = 0
        $LongestEntry = ""
        foreach ($Entry in $Archive.Entries) {
            if ($DestinationRoot) {
                $Destination = Join-Path $DestinationRoot $Entry.FullName.Replace("/", "\")
                if (-not (Test-PropExtractPathIsInside $DestinationRoot $Destination)) {
                    throw "Небезопасный путь внутри архива runtime. Скачайте проект заново."
                }
            }
            $Total += [int64]$Entry.Length
            if ($Entry.FullName.Length -gt $LongestEntry.Length) {
                $LongestEntry = $Entry.FullName
            }
        }
        return [PSCustomObject]@{ Bytes = $Total; LongestEntry = $LongestEntry }
    } catch {
        throw "Не удалось рассчитать объём распаковки архива: $Path"
    } finally {
        if ($Archive) { $Archive.Dispose() }
    }
}

function Get-PropExtractArchiveExpandedBytes([string]$Path) {
    return [int64]((Get-PropExtractArchiveMetadata $Path).Bytes)
}

function Get-PropExtractRequiredStagingBytes([string]$ProjectRoot, [object]$RuntimeLock) {
    [int64]$PythonBytes = Get-PropExtractArchiveExpandedBytes (Join-Path $ProjectRoot ([string]$RuntimeLock.artifacts.python.path))
    foreach ($Package in $RuntimeLock.pythonTree.packages) {
        $PythonBytes += Get-PropExtractArchiveExpandedBytes (Join-Path $ProjectRoot ([string]$Package.path))
    }

    [int64]$NativeBytes = Get-PropExtractArchiveExpandedBytes (Join-Path $ProjectRoot ([string]$RuntimeLock.artifacts.tesseract.path))
    $NativeBytes += Get-PropExtractArchiveExpandedBytes (Join-Path $ProjectRoot ([string]$RuntimeLock.artifacts.poppler.path))
    $NativeBytes += Get-PropExtractArchiveExpandedBytes (Join-Path $ProjectRoot ([string]$RuntimeLock.artifacts.vcruntime.path))

    # Reserve covers metadata, the temporary VC extraction and filesystem allocation overhead.
    [int64]$SafetyReserveBytes = 64MB
    return $PythonBytes + $NativeBytes + $SafetyReserveBytes
}

function Assert-PropExtractInstallerPreflight(
    [string]$ProjectRoot,
    [string]$RuntimeRoot,
    [string]$PythonRoot,
    [string]$NativeRoot,
    [object]$RuntimeLock
) {
    $MaximumRuntimePath = 240
    $ResolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path.TrimEnd("\")
    if (-not (Test-PropExtractPathIsInside $ResolvedRoot $RuntimeRoot)) {
        throw "Небезопасный путь к рабочему каталогу установки."
    }

    $RuntimeParent = Split-Path -Parent $RuntimeRoot
    foreach ($Path in @($RuntimeParent, $RuntimeRoot)) {
        if (Test-Path -LiteralPath $Path) {
            $Item = Get-Item -LiteralPath $Path -Force
            if (-not $Item.PSIsContainer) {
                throw "Небезопасный путь к рабочему каталогу установки: ожидалась папка."
            }
            if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Небезопасный путь к рабочему каталогу установки: обнаружена ссылка или точка повторной обработки."
            }
        }
    }
    foreach ($Path in @($RuntimeRoot, $PythonRoot, $NativeRoot)) {
        if ((Test-Path -LiteralPath $Path) -and (Test-PropExtractTreeContainsReparsePoint $Path)) {
            throw "Небезопасный путь к runtime: обнаружена ссылка или точка повторной обработки."
        }
    }

    $StagingId = "00000000000000000000000000000000"
    $PythonStaging = Join-Path $RuntimeRoot ("python-staging-" + $StagingId)
    $NativeStaging = Join-Path $RuntimeRoot ("native-staging-" + $StagingId)
    $PythonArchive = Join-Path $ResolvedRoot ([string]$RuntimeLock.artifacts.python.path)
    $PythonEntry = (Get-PropExtractArchiveMetadata $PythonArchive $PythonStaging).LongestEntry.Replace("/", "\")
    $PythonPackageEntry = ""
    foreach ($Package in $RuntimeLock.pythonTree.packages) {
        $PackagePath = Join-Path $ResolvedRoot ([string]$Package.path)
        $Entry = (Get-PropExtractArchiveMetadata $PackagePath (Join-Path $PythonStaging "Lib\site-packages")).LongestEntry.Replace("/", "\")
        if ($Entry.Length -gt $PythonPackageEntry.Length) { $PythonPackageEntry = $Entry }
    }
    $TesseractEntry = (Get-PropExtractArchiveMetadata (Join-Path $ResolvedRoot ([string]$RuntimeLock.artifacts.tesseract.path)) $NativeStaging).LongestEntry.Replace("/", "\")
    $PopplerEntry = (Get-PropExtractArchiveMetadata (Join-Path $ResolvedRoot ([string]$RuntimeLock.artifacts.poppler.path)) (Join-Path $NativeStaging "poppler")).LongestEntry.Replace("/", "\")
    $NativePopplerBin = Join-Path $NativeStaging ([string]$RuntimeLock.nativeTree.popplerBinPath)
    $VcRuntimeEntry = (Get-PropExtractArchiveMetadata (Join-Path $ResolvedRoot ([string]$RuntimeLock.artifacts.vcruntime.path)) $NativePopplerBin).LongestEntry.Replace("/", "\")
    $ProjectedPaths = @(
        $RuntimeRoot,
        $PythonRoot,
        (Join-Path $PythonStaging $PythonEntry),
        (Join-Path (Join-Path $PythonStaging "Lib\site-packages") $PythonPackageEntry),
        $NativeRoot,
        (Join-Path $NativeStaging $TesseractEntry),
        (Join-Path (Join-Path $NativeStaging "poppler") $PopplerEntry),
        (Join-Path $NativePopplerBin $VcRuntimeEntry),
        (Join-Path $NativeRoot (([string]$RuntimeLock.nativeTree.popplerBinPath) + "\vcruntime140.dll"))
    )
    foreach ($ProjectedPath in $ProjectedPaths) {
        try {
            $FullPath = [IO.Path]::GetFullPath($ProjectedPath)
        } catch {
            throw "Путь проекта недопустим для установки Windows runtime."
        }
        if (-not (Test-PropExtractPathIsInside $RuntimeRoot $FullPath)) {
            throw "Небезопасный путь внутри архива runtime. Скачайте проект заново."
        }
        if ($FullPath.Length -gt $MaximumRuntimePath) {
            throw "Путь проекта слишком длинный для безопасной установки. Переместите проект ближе к корню диска."
        }
    }

    $RequiredStagingBytes = Get-PropExtractRequiredStagingBytes $ResolvedRoot $RuntimeLock
    $FreeBytes = Get-PropExtractFreeBytes $ResolvedRoot
    if ($FreeBytes -lt $RequiredStagingBytes) {
        $RequiredMiB = [Math]::Ceiling($RequiredStagingBytes / 1MB)
        $FreeMiB = [Math]::Floor($FreeBytes / 1MB)
        throw "Недостаточно свободного места для установки. Требуется $RequiredMiB МБ, доступно $FreeMiB МБ на диске проекта."
    }

    Assert-PropExtractWritableDirectory $ResolvedRoot "папке проекта"
    [IO.Directory]::CreateDirectory($RuntimeRoot) | Out-Null
    Assert-PropExtractWritableDirectory $RuntimeRoot "рабочем каталоге runtime"
}

function Remove-PropExtractStaleRuntimeBackups([string]$Target, [scriptblock]$ReplacementIsVerified) {
    if (-not (& $ReplacementIsVerified $Target)) {
        Write-Warning "Очистка старых копий runtime пропущена: новая версия не прошла проверку целостности."
        return
    }

    $Parent = Split-Path -Parent $Target
    $TargetName = Split-Path -Leaf $Target
    $Pattern = "^" + [regex]::Escape($TargetName) + "\.invalid\.\d{8}-\d{6}\.[0-9a-f]{32}$"
    foreach ($Candidate in @(Get-ChildItem -LiteralPath $Parent -Directory -Force -ErrorAction SilentlyContinue)) {
        if ($Candidate.Name -notmatch $Pattern) { continue }
        if (($Candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Warning "Старая копия runtime пропущена: обнаружена ссылка или точка повторной обработки."
            continue
        }
        if (-not (Test-PropExtractPathIsInside $Parent $Candidate.FullName)) {
            Write-Warning "Старая копия runtime пропущена: путь находится вне рабочего каталога."
            continue
        }
        try {
            Remove-Item -LiteralPath $Candidate.FullName -Recurse -Force -ErrorAction Stop
            Write-Host "Удалена проверенная старая копия runtime: $($Candidate.Name)"
        } catch {
            Write-Warning "Не удалось удалить старую копию runtime: $($Candidate.Name)"
        }
    }
}

function Test-PropExtractFileSha256([string]$Path, [string]$Expected) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        return $Actual -eq $Expected.ToLowerInvariant()
    } catch {
        return $false
    }
}

function Get-PropExtractDirectoryDigest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return [PSCustomObject]@{ Sha256 = ""; Files = 0 }
    }
    if (Test-PropExtractTreeContainsReparsePoint $Path) {
        return [PSCustomObject]@{ Sha256 = ""; Files = 0 }
    }
    $ResolvedRoot = (Resolve-Path -LiteralPath $Path).Path.TrimEnd("\")
    $Files = @(Get-ChildItem -LiteralPath $ResolvedRoot -File -Recurse)
    [string[]]$RelativePaths = @(
        $Files | ForEach-Object {
            $_.FullName.Substring($ResolvedRoot.Length).TrimStart("\").Replace("\", "/")
        }
    )
    [Array]::Sort($RelativePaths, [StringComparer]::Ordinal)
    $Lines = New-Object System.Collections.Generic.List[string]
    foreach ($RelativePath in $RelativePaths) {
        $FilePath = Join-Path $ResolvedRoot ($RelativePath.Replace("/", "\"))
        $Hash = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $Lines.Add("$Hash  $RelativePath")
    }
    $Canonical = [string]::Join("`n", $Lines) + "`n"
    $Sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $Bytes = [Text.Encoding]::UTF8.GetBytes($Canonical)
        $DigestBytes = $Sha256.ComputeHash($Bytes)
        $Digest = ([BitConverter]::ToString($DigestBytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $Sha256.Dispose()
    }
    return [PSCustomObject]@{ Sha256 = $Digest; Files = $RelativePaths.Count }
}

function Get-PropExtractNativeTool([string]$RootPath, [string]$Name, [object]$RuntimeLock) {
    if (Test-PropExtractTreeContainsReparsePoint $RootPath) { return $null }
    if ($Name -eq "tesseract") {
        $RelativePath = [string]$RuntimeLock.nativeTree.tesseractPath
    } else {
        $RelativePath = Join-Path ([string]$RuntimeLock.nativeTree.popplerBinPath) ("$Name.exe")
    }
    $Candidate = Join-Path $RootPath $RelativePath
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $null }
    return Get-Item -LiteralPath $Candidate
}

function Test-PropExtractNativeTree([string]$Path, [object]$RuntimeLock) {
    $Digest = Get-PropExtractDirectoryDigest $Path
    return (
        $Digest.Files -eq [int]$RuntimeLock.nativeTree.files -and
        $Digest.Sha256 -eq [string]$RuntimeLock.nativeTree.sha256
    )
}

function Test-PropExtractPythonTree([string]$Path, [object]$RuntimeLock) {
    $Digest = Get-PropExtractDirectoryDigest $Path
    return (
        $Digest.Files -eq [int]$RuntimeLock.pythonTree.files -and
        $Digest.Sha256 -eq [string]$RuntimeLock.pythonTree.sha256
    )
}
