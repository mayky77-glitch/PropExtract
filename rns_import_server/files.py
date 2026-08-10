"""Safe input-file discovery shared by the UI and processing pipeline."""
from __future__ import annotations

import os
from pathlib import Path


def discover_pdfs(folder: Path) -> list[Path]:
    """Find regular PDF files case-insensitively without following symlink folders."""
    errors: list[OSError] = []

    def record_error(error: OSError) -> None:
        errors.append(error)

    found: list[Path] = []
    for current, directories, filenames in os.walk(folder, topdown=True, onerror=record_error, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories if not (current_path / name).is_symlink()]
        for filename in filenames:
            candidate = current_path / filename
            if candidate.suffix.casefold() == ".pdf" and candidate.is_file() and not candidate.is_symlink():
                found.append(candidate)
    if errors:
        location = getattr(errors[0], "filename", None) or str(folder)
        raise ValueError(f"Не удалось прочитать папку с PDF: {location}") from errors[0]
    return sorted(found, key=lambda path: str(path).casefold())
