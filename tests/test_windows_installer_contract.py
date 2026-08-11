from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_powershell_51_reads_russian_scripts_as_utf8():
    bom = b"\xef\xbb\xbf"

    assert (ROOT / "install_windows.ps1").read_bytes().startswith(bom)
    assert (ROOT / "windows_runtime_helpers.ps1").read_bytes().startswith(bom)


def test_windows_end_to_end_result_is_safe_for_legacy_console_codepages():
    smoke = (ROOT / "scripts" / "windows_end_to_end_smoke.py").read_text(encoding="utf-8")

    assert "print(json.dumps(result, ensure_ascii=True, sort_keys=True))" in smoke


def test_windows_installer_serializes_runs_and_releases_mutex_in_finally():
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")
    helpers = (ROOT / "windows_runtime_helpers.ps1").read_text(encoding="utf-8")

    assert r'"Local\PropExtractInstaller-"' in helpers
    assert r'"Local\\PropExtractInstaller-"' not in helpers
    assert "System.Threading.Mutex" in helpers
    assert "$Mutex.WaitOne(0)" in helpers
    assert "Установка уже выполняется для этой папки проекта" in helpers
    assert "$script:InstallerMutexHeld = Enter-PropExtractInstallerMutex" in installer
    assert "finally {" in installer
    assert "$script:InstallerMutex.ReleaseMutex()" in installer
    assert "$script:InstallerMutex.Dispose()" in installer


def test_windows_installer_preflight_rejects_unsafe_unwritable_low_space_and_long_paths():
    helpers = (ROOT / "windows_runtime_helpers.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")

    assert "Assert-PropExtractInstallerPreflight" in helpers
    assert "Assert-PropExtractInstallerPreflight $Root $RuntimeRoot $PythonRoot $NativeRoot $RuntimeLock" in installer
    assert "Test-PropExtractPathIsInside" in helpers
    assert "ReparsePoint" in helpers
    assert "function Test-PropExtractTreeContainsReparsePoint" in helpers
    assert "System.Collections.Generic.Stack[string]" in helpers
    assert "Get-ChildItem -LiteralPath $Current.FullName -Force" in helpers
    assert "foreach ($Path in @($RuntimeRoot, $PythonRoot, $NativeRoot))" in helpers
    assert "Test-PropExtractTreeContainsReparsePoint $Path" in helpers
    assert "Assert-PropExtractWritableDirectory" in helpers
    assert "[IO.File]::Open(" in helpers
    assert "[IO.FileMode]::CreateNew" in helpers
    assert "[IO.Directory]::CreateDirectory($RuntimeRoot)" in helpers
    assert "New-Item -ItemType File -LiteralPath" not in helpers
    assert "New-Item -ItemType Directory -LiteralPath" not in helpers
    assert "Get-PropExtractRequiredStagingBytes" in helpers
    assert "Get-PropExtractArchiveExpandedBytes" in helpers
    assert "$SafetyReserveBytes = 64MB" in helpers
    assert "return $PythonBytes + $NativeBytes + $SafetyReserveBytes" in helpers
    assert "$MaximumRuntimePath = 240" in helpers
    assert "Get-PropExtractArchiveMetadata" in helpers
    assert "$PythonEntry" in helpers
    assert "$TesseractEntry" in helpers
    assert "$PopplerEntry" in helpers
    assert "foreach ($Entry in $Archive.Entries)" in helpers
    assert "Test-PropExtractPathIsInside $DestinationRoot $Destination" in helpers
    assert "Небезопасный путь внутри архива runtime" in helpers
    assert 'Equals($ParentFull, [StringComparison]::OrdinalIgnoreCase)' in helpers
    assert r'($ParentFull + "\")' in helpers
    assert r'TrimEnd("\\")' not in helpers
    assert "Путь проекта слишком длинный" in helpers
    assert "Недостаточно свободного места" in helpers


def test_runtime_digest_and_native_tool_reject_nested_reparse_points():
    helpers = (ROOT / "windows_runtime_helpers.ps1").read_text(encoding="utf-8")

    digest = helpers.index("function Get-PropExtractDirectoryDigest")
    digest_reparse = helpers.index("Test-PropExtractTreeContainsReparsePoint $Path", digest)
    digest_enumeration = helpers.index("Get-ChildItem -LiteralPath $ResolvedRoot -File -Recurse", digest)
    native_tool = helpers.index("function Get-PropExtractNativeTool")
    native_reparse = helpers.index("Test-PropExtractTreeContainsReparsePoint $RootPath", native_tool)
    native_candidate = helpers.index("$Candidate = Join-Path $RootPath", native_tool)

    assert digest < digest_reparse < digest_enumeration
    assert native_tool < native_reparse < native_candidate


def test_windows_installer_rolls_back_failed_publication_and_cleans_only_verified_backups():
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")
    helpers = (ROOT / "windows_runtime_helpers.ps1").read_text(encoding="utf-8")

    assert "function Publish-RuntimeTree" in installer
    assert "[scriptblock]$TargetIsVerified" in installer
    assert "if (-not (& $TargetIsVerified $Target))" in installer
    assert "publish-failed" in installer
    assert "Move-Item -LiteralPath $Backup -Destination $Target" in installer
    assert "function Remove-PropExtractStaleRuntimeBackups" in helpers
    assert "ReplacementIsVerified" in helpers
    assert "if (-not (& $ReplacementIsVerified $Target))" in helpers
    assert r'"\.invalid\.\d{8}-\d{6}\.[0-9a-f]{32}$"' in helpers
    assert r'"\\.invalid\\.\\d{8}-\\d{6}\\.[0-9a-f]{32}$"' not in helpers
    assert "Get-ChildItem -LiteralPath $Parent -Directory -Force" in helpers
    assert "Remove-PropExtractStaleRuntimeBackups $PythonRoot" in installer
    assert "Remove-PropExtractStaleRuntimeBackups $NativeRoot" in installer
    assert "Test-PropExtractPythonTree" in installer
    assert "Test-PropExtractNativeTree" in installer


def test_windows_installer_keeps_offline_no_uac_and_russian_failure_contract():
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")
    command = (ROOT / "install_windows.cmd").read_text(encoding="utf-8")

    for forbidden in ("Invoke-WebRequest", "WebClient", "Start-BitsTransfer", "winget source reset", "winget install"):
        assert forbidden.lower() not in installer.lower()
    assert "-Verb RunAs" not in command
    assert "ОШИБКА УСТАНОВКИ" in installer
    assert "Установка завершилась с ошибкой" in command


def test_windows_installer_preserves_preflight_failure_for_console_and_transcript():
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")

    mutex = installer.index("Enter-PropExtractInstallerMutex")
    transcript = installer.index("Start-Transcript")
    preflight = installer.index("Assert-PropExtractInstallerPreflight $Root")
    assert mutex < transcript < preflight
    assert 'Write-Host "`nОШИБКА УСТАНОВКИ: $($_.Exception.Message)"' in installer
    assert 'throw "Установка остановлена.' not in installer
