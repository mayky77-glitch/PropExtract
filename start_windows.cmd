@echo off
setlocal
cd /d "%~dp0"
set "PROPEXTRACT_PYTHON=.venv\Scripts\python.exe"
if not exist "%PROPEXTRACT_PYTHON%" (
  echo Virtual environment not found. Run: py -m venv .venv
  echo Then run: .venv\Scripts\python.exe -m pip install -r requirements-rns-import.txt
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8775"
"%PROPEXTRACT_PYTHON%" -m rns_import_server.app serve --host 127.0.0.1 --port 8775
endlocal
