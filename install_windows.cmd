@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation failed. See error above.
  if not defined CI pause
  exit /b 1
)
endlocal
