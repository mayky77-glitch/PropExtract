Set-StrictMode -Version 2.0

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
