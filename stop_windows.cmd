@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_windows.ps1"
set "PROPEXTRACT_EXIT=%ERRORLEVEL%"
if not defined CI pause
exit /b %PROPEXTRACT_EXIT%
