@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows.ps1" %*
if errorlevel 1 (
  echo.
  echo PropExtract failed to start. Run install_windows.cmd again.
  if not defined CI pause
  exit /b 1
)
endlocal
