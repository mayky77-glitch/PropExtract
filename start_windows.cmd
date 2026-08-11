@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File ".\start_windows.ps1" %*
set "PROPEXTRACT_EXIT=%ERRORLEVEL%"
popd
endlocal & exit /b %PROPEXTRACT_EXIT%
