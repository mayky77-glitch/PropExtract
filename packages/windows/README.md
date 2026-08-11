# Windows runtime artifacts

These versioned public artifacts make the PropExtract installer independent of
WinGet, administrator rights, system Python and external downloads after the
repository has been obtained. `install_windows.ps1` checks every SHA-256 value
from `windows-runtime.lock.json` before extraction and verifies complete runtime
tree digests before first execution.

- Python 3.12.10 x64 is the unmodified embeddable archive from python.org (PSF License).
- Poppler 25.07.0-0 is the unmodified archive from `oschwartz10612/poppler-windows`.
- Tesseract 5.5.3 portable is built by extracting the official upstream NSIS
  artifact and retaining `tesseract.exe`, its adjacent DLLs and upstream license
  files. The OCR engine is Apache-2.0; bundled third-party libraries retain
  their upstream licenses.
- `vc_runtimeMinimum_x64.zip` contains the 12 app-local DLL payloads extracted
  without modification from Microsoft's x64 minimum-runtime CAB for Visual C++
  Redistributable 14.51.36247.0. ZIP avoids the legacy native CAB extractor,
  which cannot receive Cyrillic project paths from Windows PowerShell 5.1.
  The ZIP SHA-256, source CAB SHA-256 and upstream redistributable SHA-256 are
  pinned in the lock file; the DLLs are deployed beside Poppler without a
  machine-level installation.

Exact upstream URLs and hashes are recorded in `windows-runtime.lock.json`.
`scripts/build_windows_python_runtime.py` and
`scripts/build_windows_tesseract_runtime.py` reproduce the two custom runtime
layouts and their canonical directory digests.
