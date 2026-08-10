"""Native file and directory picker, launched in its own GUI process."""
from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def _choose_macos(kind: str) -> str:
    if kind == "directory":
        script = 'POSIX path of (choose folder with prompt "Выберите папку с PDF")'
    else:
        script = (
            'POSIX path of (choose file with prompt "Выберите целевой файл Excel" '
            'of type {"org.openxmlformats.spreadsheetml.sheet"})'
        )
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        if "(-128)" in result.stderr:
            return ""
        raise RuntimeError("macos_picker_failed")
    return str(Path(result.stdout.strip()).resolve()) if result.stdout.strip() else ""


def _windows_system_directory() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise RuntimeError("windows_system_directory_unavailable")
    return Path(buffer.value)


def _choose_windows(kind: str) -> str:
    powershell = _windows_system_directory() / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        raise RuntimeError("windows_powershell_unavailable")

    dialog = (
        "$Dialog = New-Object System.Windows.Forms.FolderBrowserDialog\n"
        "$Dialog.Description = 'Выберите папку с PDF'\n"
        "$Dialog.ShowNewFolderButton = $false\n"
        if kind == "directory"
        else
        "$Dialog = New-Object System.Windows.Forms.OpenFileDialog\n"
        "$Dialog.Title = 'Выберите целевой файл Excel'\n"
        "$Dialog.Filter = 'Книга Excel (*.xlsx)|*.xlsx'\n"
        "$Dialog.CheckFileExists = $true\n"
        "$Dialog.Multiselect = $false\n"
    )
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "$Utf8 = New-Object System.Text.UTF8Encoding($false)\n"
        "[Console]::OutputEncoding = $Utf8\n"
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "$Owner = New-Object System.Windows.Forms.Form\n"
        "$Owner.TopMost = $true\n"
        "$Owner.ShowInTaskbar = $false\n"
        "$Owner.StartPosition = 'Manual'\n"
        "$Owner.Opacity = 0\n"
        f"{dialog}"
        "try {\n"
        "  $null = $Owner.Show()\n"
        "  $null = $Owner.Activate()\n"
        "  $Result = $Dialog.ShowDialog($Owner)\n"
        "  if ($Result -eq [System.Windows.Forms.DialogResult]::OK) {\n"
        "    if ($Dialog -is [System.Windows.Forms.FolderBrowserDialog]) { $Dialog.SelectedPath } else { $Dialog.FileName }\n"
        "  }\n"
        "} finally {\n"
        "  $Dialog.Dispose()\n"
        "  $Owner.Dispose()\n"
        "}\n"
    )
    result = subprocess.run(
        [str(powershell), "-NoLogo", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError("windows_picker_failed")
    return str(Path(result.stdout.strip()).resolve()) if result.stdout.strip() else ""


def choose(kind: str) -> str:
    if kind not in {"directory", "xlsx"}:
        raise ValueError("unknown picker kind")
    if sys.platform == "darwin":
        return _choose_macos(kind)
    if sys.platform == "win32":
        return _choose_windows(kind)
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:
        raise RuntimeError("tkinter_unavailable") from error

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    root.update()
    try:
        if kind == "directory":
            selected = filedialog.askdirectory(
                parent=root,
                title="Выберите папку с PDF",
                mustexist=True,
            )
        else:
            selected = filedialog.askopenfilename(
                parent=root,
                title="Выберите целевой файл Excel",
                filetypes=(("Книга Excel", "*.xlsx"),),
            )
    finally:
        root.destroy()
    return str(Path(selected).resolve()) if selected else ""


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m rns_import_server.picker directory|xlsx")
    try:
        print(choose(sys.argv[1]), flush=True)
    except Exception as error:
        print(str(error), file=sys.stderr, flush=True)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
