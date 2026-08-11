import json
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


def test_vc_runtime_uses_unicode_safe_verified_zip():
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")
    helpers = (ROOT / "windows_runtime_helpers.ps1").read_text(encoding="utf-8")
    lock = json.loads((ROOT / "windows-runtime.lock.json").read_text(encoding="utf-8"))
    artifact = lock["artifacts"]["vcruntime"]
    archive = ROOT / artifact["path"]

    assert archive.suffix == ".zip"
    with ZipFile(archive) as package:
        names = package.namelist()
    assert len(names) == artifact["files"] == 12
    assert "vcruntime140.dll" in names
    assert "msvcp140.dll" in names
    assert all(name.endswith(".dll") and "_amd64" not in name for name in names)
    assert "Expand-Archive -LiteralPath $VcRuntimeArchive -DestinationPath $PopplerBin -Force" in installer
    assert "expand.exe" not in installer.lower()
    assert "$VcRuntimeEntry" in helpers


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

    workflow = (ROOT / ".github" / "workflows" / "windows-smoke.yml").read_text(encoding="utf-8")
    assert "$exitCode -eq 0 -or $elapsed -gt 10" in workflow
    assert '$output -notmatch "Установка уже выполняется"' not in workflow
    assert "$global:LASTEXITCODE = 0" in workflow
    assert "Test-PropExtractTreeContainsReparsePoint $junction" in workflow
    assert '$_.Exception.Message -match "точка повторной обработки"' not in workflow


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
    assert "$VcRuntimeEntry" in helpers
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

    for forbidden in ("Invoke-WebRequest", "WebClient", "Start-BitsTransfer", "winget source reset", "winget install"):
        assert forbidden.lower() not in installer.lower()
    assert "ОШИБКА УСТАНОВКИ" in installer


def test_windows_cmd_launcher_survives_shell_execute_from_paths_with_cmd_metacharacters():
    launchers = {
        "install_windows.cmd": ' -File ".\\install_windows.ps1" %*',
        "start_windows.cmd": ' -File ".\\start_windows.ps1" %*',
        "stop_windows.cmd": ' -File ".\\stop_windows.ps1"',
        "Запустить PropExtract.cmd": 'call ".\\start_windows.cmd" %*',
        "Остановить PropExtract.cmd": 'call ".\\stop_windows.cmd"',
    }
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    for name, invocation in launchers.items():
        command = (ROOT / name).read_bytes()
        text = command.decode("ascii")

        assert command.isascii()
        assert b"\r\n" in command
        assert b"\n" not in command.replace(b"\r\n", b"")
        attribute_pattern = name.replace(" ", "?")
        assert f"{attribute_pattern} -text whitespace=cr-at-eol" in attributes
        assert "setlocal DisableDelayedExpansion" in text
        assert 'pushd "%~dp0" || exit /b 1' in text
        assert invocation in text
        assert "%~dp0install_windows.ps1" not in text
        assert "%~dp0start_windows.ps1" not in text
        assert "%~dp0stop_windows.ps1" not in text
        assert 'set "PROPEXTRACT_EXIT=%ERRORLEVEL%"' in text
        assert "popd" in text
        assert "endlocal & exit /b %PROPEXTRACT_EXIT%" in text
        assert "-Verb RunAs" not in text

    for name in ("install_windows.cmd", "start_windows.cmd"):
        text = (ROOT / name).read_text(encoding="ascii")
        assert 'if not "%PROPEXTRACT_EXIT%"=="0" if not defined CI pause' in text

    stop = (ROOT / "stop_windows.cmd").read_text(encoding="ascii")
    assert "if not defined CI pause" in stop
    for name in ("Запустить PropExtract.cmd", "Остановить PropExtract.cmd"):
        assert "pause" not in (ROOT / name).read_text(encoding="ascii")


def test_windows_installer_preserves_preflight_failure_for_console_and_transcript():
    installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")

    mutex = installer.index("Enter-PropExtractInstallerMutex")
    transcript = installer.index("Start-Transcript")
    preflight = installer.index("Assert-PropExtractInstallerPreflight $Root")
    assert mutex < transcript < preflight
    assert 'Write-Host "`nОШИБКА УСТАНОВКИ: $($_.Exception.Message)"' in installer
    assert 'throw "Установка остановлена.' not in installer
