@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
call ".\stop_windows.cmd"
set "PROPEXTRACT_EXIT=%ERRORLEVEL%"
popd
endlocal & exit /b %PROPEXTRACT_EXIT%
