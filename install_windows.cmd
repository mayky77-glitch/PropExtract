@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File ".\install_windows.ps1" %*
set "PROPEXTRACT_EXIT=%ERRORLEVEL%"
popd
if not "%PROPEXTRACT_EXIT%"=="0" if not defined CI pause
endlocal & exit /b %PROPEXTRACT_EXIT%
