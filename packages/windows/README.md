# Windows runtime artifacts

These versioned public artifacts make the PropExtract installer independent of
WinGet, administrator rights and external downloads after the repository has
been obtained. `install_windows.ps1` checks every SHA-256 value from
`windows-runtime.lock.json` before execution or extraction.

- Python 3.12.10 x64 is the unmodified installer from python.org (PSF License).
- Poppler 25.07.0-0 is the unmodified archive from `oschwartz10612/poppler-windows`.
- Tesseract 5.5.3 portable is built by extracting the official upstream NSIS
  artifact and retaining `tesseract.exe`, its adjacent DLLs and upstream license
  files. The OCR engine is Apache-2.0; bundled third-party libraries retain
  their upstream licenses.
- `vc_runtimeMinimum_x64.cab` is the unmodified x64 minimum-runtime payload from
  Microsoft Visual C++ Redistributable 14.51.36247.0. It is deployed app-local
  beside Poppler, so no machine-level installation is needed.

Exact upstream URLs and hashes are recorded in `windows-runtime.lock.json`.
