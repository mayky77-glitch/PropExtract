"""Cross-platform runtime diagnostics used by installers and the admin UI."""
from __future__ import annotations

import json
import subprocess

try:
    from rns_import_server.ocr import (
        PROJECT_ROOT,
        _is_windows,
        _native_argv,
        _native_environment,
        _run,
        bundled_language_status,
        find_tool,
        tesseract_environment,
    )
except ModuleNotFoundError:
    from ocr import (
        PROJECT_ROOT,
        _is_windows,
        _native_argv,
        _native_environment,
        _run,
        bundled_language_status,
        find_tool,
        tesseract_environment,
    )


def _is_supported_tesseract_version(version: str | None) -> bool:
    if not version:
        return False
    return version.lower().startswith(("tesseract 5.", "tesseract v5."))


def runtime_status() -> dict[str, object]:
    issues: list[dict[str, str]] = []

    def _add_issue(code: str, message: str) -> None:
        normalized = message.strip()
        if normalized:
            issues.append({"code": code, "message": normalized})

    paths = {name: find_tool(name) for name in ("tesseract", "pdfinfo", "pdftoppm", "pdftotext")}
    missing_commands = [name for name, path in paths.items() if not path]
    languages: list[str] = []
    version = None
    if paths["tesseract"]:
        native_workspace = PROJECT_ROOT if _is_windows() else None
        try:
            version_result = _run(
                _native_argv(str(paths["tesseract"]), ["--version"], native_workspace),
                timeout=10,
                env=_native_environment(native_workspace),
                cwd=native_workspace,
            )
            version = (version_result.stdout or version_result.stderr).splitlines()[0].strip()
            language_result = _run(
                _native_argv(str(paths["tesseract"]), ["--list-langs"], native_workspace),
                timeout=10,
                env=(
                    tesseract_environment(native_workspace)
                    if native_workspace is not None
                    else tesseract_environment()
                ),
                cwd=native_workspace,
            )
            languages = [line.strip() for line in language_result.stdout.splitlines()[1:] if line.strip()]
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            _add_issue("tesseract_probe_failed", str(error))
    else:
        _add_issue("runtime_command_missing", "Tesseract не найден в PATH или portable-runtime.")

    if missing_commands:
        _add_issue(
            "runtime_command_missing",
            "Не найдены команды: " + ", ".join(f"{item}" for item in sorted(missing_commands)),
        )

    if not version:
        _add_issue("tesseract_version_missing", "Не удалось определить версию Tesseract.")
    models = bundled_language_status()
    required_commands = all(paths[name] for name in ("tesseract", "pdfinfo", "pdftoppm"))
    models_valid = all(bool(item["valid"]) for item in models.values())
    required_languages = {"rus", "eng"}.issubset(languages)
    tesseract_5 = _is_supported_tesseract_version(version)

    if not models_valid:
        invalid = ", ".join(sorted(name for name, item in models.items() if not bool(item.get("valid"))))
        _add_issue("runtime_model_invalid", f"Неверные или отсутствующие языковые модели: {invalid or 'rus/eng'}")
    if required_commands and not required_languages:
        _add_issue("runtime_language_missing", "Не установлены обязательные языки rus/eng в Tesseract.")
    if version and not tesseract_5:
        _add_issue("runtime_tesseract_version", "Неподдерживаемая версия Tesseract, требуется 5.x")

    issue_codes = list(dict.fromkeys(item["code"] for item in issues))
    return {
        "ready": bool(required_commands and models_valid and required_languages and tesseract_5),
        "commands": {key: bool(value) for key, value in paths.items()},
        "languages": languages,
        "models": models,
        "tesseract_version": version,
        "issues": issues,
        "issue_codes": issue_codes,
    }


def main() -> None:
    status = runtime_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not status["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
