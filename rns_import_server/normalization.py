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
_LEGACY_RNS = re.compile(
    r"(?<![0-9A-Za-zА-Яа-я])(?:38|3[ВB]|З8)[\s_\-–—]*(\d{1,2})[\s_\-–—]*(\d{1,2})[\s_\-–—]*(20\d{2})(?!\d)",
    re.IGNORECASE,
)
_COMPACT_RNS = re.compile(r"(?<!\d)(?:38|3[ВB]|З8)(\d{1,2})(\d{1,2})(20\d{2})(?!\d)", re.IGNORECASE)
_MODERN_RNS = re.compile(
    r"(?<![0-9A-Za-zА-Яа-я])(?:RU|R[УY]|Р[УY])[\s_\-–—]*(\d{8})[\s_\-–—]*(\d{2})[\s_\-–—]*(20\d{2})(?!\d)",
    re.IGNORECASE,
)


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


def canonical_rns_identities(value: object) -> tuple[str, ...]:
    """Return complete explicit RNS identities, preserving no presentation text.

    OCR commonly confuses Cyrillic/Latin look-alikes in the fixed ``38`` and
    ``RU`` prefixes.  Only those fixed characters are repaired; variable
    numeric groups are never guessed or padded.
    """
    # NFKC expands ``№`` to ``No``.  Neutralize it first so an adjacent RNS
    # prefix retains its boundary (for example, ``№RU-...``).
    source = normalize_text(str(value).replace("№", " ") if value is not None else "", casefold=False) or ""
    identities: list[tuple[int, str]] = []
    for pattern, formatter in (
        (_LEGACY_RNS, lambda match: f"38-{match.group(1)}-{match.group(2)}-{match.group(3)}"),
        (_COMPACT_RNS, lambda match: f"38-{match.group(1)}-{match.group(2)}-{match.group(3)}"),
        (_MODERN_RNS, lambda match: f"RU-{match.group(1)}-{match.group(2)}-{match.group(3)}"),
    ):
        identities.extend((match.start(), formatter(match)) for match in pattern.finditer(source))
    identities.sort(key=lambda item: item[0])
    return tuple(dict.fromkeys(identity for _, identity in identities))


def canonical_rns_identity(value: object) -> str | None:
    """Return one identity only; absence and ambiguity remain visible to caller."""
    identities = canonical_rns_identities(value)
    return identities[0] if len(identities) == 1 else None
