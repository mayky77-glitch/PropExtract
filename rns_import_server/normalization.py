"""Conservative text normalization shared by Excel/PDF comparisons.

The base ``normalize_text`` contract is adapted from Document Optimizer's
``report_processor.training_data.normalization`` module.  PropExtract adds
only quote-insensitive comparison on top; it does not infer synonyms.
"""
from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")
_QUOTES_RE = re.compile(r"[«»„“”\"']")


def normalize_text(value: str | None, *, casefold: bool = True) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).replace("\u00a0", " ")
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return None
    return text.casefold() if casefold else text


def normalize_comparison_text(value: str | None) -> str:
    """Normalize harmless presentation differences without changing meaning."""
    normalized = normalize_text(value) or ""
    normalized = _QUOTES_RE.sub("", normalized)
    return normalized.strip(" .,;:")
