"""Disk-safe report projection shared by report writers and finalization."""
from __future__ import annotations

# Kept in a dedicated module so the finalization authority never imports the
# application runtime.  The implementation is moved verbatim from app.py.
import ntpath
import re

_QUOTED_LOCAL_PATH = re.compile(r"(?P<quote>['\"])(?P<path>(?:[A-Z]:[\\/]|\\\\[^\\/\r\n'\"]+[\\/][^\\/\r\n'\"]+|/)[^'\"\r\n]*)(?P=quote)", re.IGNORECASE)
_UNQUOTED_POSIX_PATH_WITH_SPACES = re.compile(r"(?<![:\w])/(?:[^/\s:'\"<>|]+/)+(?:[^\s,;:'\"<>|]+(?:\s+[^\s,;:'\"<>|]+)*/)*(?:[^\s,;:'\"<>|]+)?")
_WINDOWS_PATH_IN_TEXT = re.compile(r"(?i)(?<![0-9A-ZА-ЯЁ])(?:[A-Z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+[\\/])(?:[^\\/:*?\"<>|'\r\n]+[\\/])*[^\\/:*?\"<>|'\r\n]+")
_POSIX_PATH_IN_TEXT = re.compile(r"(?<![:\w])/(?:[^/\s:'\"<>|]+/)*[^/\s:'\"<>|]+")
_REPORT_OMITTED_KEYS = frozenset({"authorization", "capability", "captured_text", "ocr_output", "ocr_text", "password", "raw_ocr_text", "raw_text", "secret", "stderr", "stdout", "text", "token"})
_REPORT_DIAGNOSTIC_KEYS = frozenset({"error", "technical_error", "message"})


def _safe_report_string(value: str, key: str | None) -> str:
    if value.startswith("/") or ntpath.isabs(value):
        normalized = value.replace("/", "\\")
        if re.fullmatch(r"[A-Za-z]:\\*|\\\\[^\\]+\\[^\\]+\\*", normalized):
            return "[локальный путь]"
        return ntpath.basename(normalized.rstrip("\\")) or "[локальный путь]"
    if (key or "").casefold() in _REPORT_DIAGNOSTIC_KEYS:
        value = _QUOTED_LOCAL_PATH.sub(lambda match: f"{match.group('quote')}[локальный путь]{match.group('quote')}", value)
        value = _UNQUOTED_POSIX_PATH_WITH_SPACES.sub("[локальный путь]", value)
        value = _WINDOWS_PATH_IN_TEXT.sub("[локальный путь]", value)
        value = _POSIX_PATH_IN_TEXT.sub("[локальный путь]", value)
    return value


def safe_report_projection(value: object, key: str | None = None) -> object:
    normalized_key = (key or "").casefold()
    if normalized_key in _REPORT_OMITTED_KEYS:
        return None
    if isinstance(value, dict):
        projected: dict[str, object] = {}
        for index, (item_key, item_value) in enumerate(value.items(), start=1):
            original_key = str(item_key)
            if original_key.casefold() in _REPORT_OMITTED_KEYS:
                continue
            safe_key = _safe_report_string(original_key, "message")
            if safe_key in projected:
                safe_key = f"{safe_key} ({index})"
            projected[safe_key] = safe_report_projection(item_value, original_key)
        return projected
    if isinstance(value, (list, tuple)):
        return [safe_report_projection(item, key) for item in value]
    return _safe_report_string(value, key) if isinstance(value, str) else value
