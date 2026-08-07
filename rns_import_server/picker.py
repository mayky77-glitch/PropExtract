"""Native file and directory picker, launched in its own GUI process."""
from __future__ import annotations

import sys
import subprocess
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


def choose(kind: str) -> str:
    if kind not in {"directory", "xlsx"}:
        raise ValueError("unknown picker kind")
    if sys.platform == "darwin":
        return _choose_macos(kind)
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
