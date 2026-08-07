"""Cross-platform runtime diagnostics used by installers and the admin UI."""
from __future__ import annotations

import json
import shutil
import subprocess

try:
    from rns_import_server.ocr import bundled_language_status, tesseract_environment
except ModuleNotFoundError:
    from ocr import bundled_language_status, tesseract_environment


def runtime_status() -> dict[str, object]:
    paths = {name: shutil.which(name) for name in ("tesseract", "pdfinfo", "pdftoppm", "pdftotext")}
    languages: list[str] = []
    version = None
    if paths["tesseract"]:
        try:
            version_result = subprocess.run(
                [str(paths["tesseract"]), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            version = (version_result.stdout or version_result.stderr).splitlines()[0].strip()
            language_result = subprocess.run(
                [str(paths["tesseract"]), "--list-langs"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=tesseract_environment(),
            )
            languages = [line.strip() for line in language_result.stdout.splitlines()[1:] if line.strip()]
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass
    models = bundled_language_status()
    required_commands = all(paths[name] for name in ("tesseract", "pdfinfo", "pdftoppm"))
    models_valid = all(bool(item["valid"]) for item in models.values())
    required_languages = {"rus", "eng"}.issubset(languages)
    tesseract_5 = bool(version and version.lower().startswith("tesseract 5."))
    return {
        "ready": bool(required_commands and models_valid and required_languages and tesseract_5),
        "commands": {key: bool(value) for key, value in paths.items()},
        "languages": languages,
        "models": models,
        "tesseract_version": version,
    }


def main() -> None:
    status = runtime_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not status["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
