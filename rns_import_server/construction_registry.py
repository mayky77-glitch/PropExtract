"""Construction registry value objects and exact, explainable matching.

This module deliberately has no Excel or HTTP dependencies.  The runtime
registry stores only semantic construction identities; physical workbook
coordinates are resolved by a later workbook consumer on every operation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from rns_import_server.normalization import normalize_text


CODE_PREFIX_RE = re.compile(r"^[0-9]{3}-[0-9]{7}$")
STATUSES = frozenset({"draft", "active", "archived"})
# A prefix may be followed by whitespace or punctuation, but never another
# letter/digit.  It makes a match auditable and prevents partial-word routing.
_BOUNDARY_CHARS = frozenset(".,;:!?)]}>»\"'/\\-—–")


class ConstructionValidationError(ValueError):
    """A registry construction breaks the fixed v1 grammar."""


@dataclass(frozen=True)
class Construction:
    """A semantic construction record returned by the registry."""

    id: str
    seed_entry_id: str | None
    origin: str
    code_prefix: str
    official_name: str
    normalized_name: str
    status: str
    row_revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ConstructionMatch:
    construction: Construction
    object_tail: str


def normalized_official_name(value: str) -> str:
    normalized = normalize_text(value)
    if not normalized:
        raise ConstructionValidationError("Официальное наименование стройки не может быть пустым")
    return normalized


def validate_construction_values(code_prefix: str, official_name: str, status: str) -> tuple[str, str]:
    if not isinstance(code_prefix, str) or not CODE_PREFIX_RE.fullmatch(code_prefix):
        raise ConstructionValidationError("Код стройки должен иметь формат 000-0000000")
    normalized = normalized_official_name(official_name)
    if status not in STATUSES:
        raise ConstructionValidationError("Недопустимый статус стройки")
    return code_prefix, normalized


def match_official_prefix(
    pdf_object: str | None,
    constructions: Iterable[Construction],
    *,
    include_archived: bool = False,
) -> ConstructionMatch | None:
    """Match one official normalized name at the beginning of a PDF object.

    Matching is exact after the same Unicode/whitespace normalization used by
    the registry.  Nested names are legal: selecting the longest valid prefix
    avoids routing a more specific official name to its parent.  There is no
    fuzzy or substring fallback.
    """
    normalized_object = normalize_text(pdf_object, casefold=True)
    if not normalized_object:
        return None
    candidates: list[Construction] = []
    for construction in constructions:
        if construction.status == "archived" and not include_archived:
            continue
        prefix = construction.normalized_name
        if not normalized_object.startswith(prefix):
            continue
        remainder = normalized_object[len(prefix):]
        if remainder and not (remainder[0].isspace() or remainder[0] in _BOUNDARY_CHARS):
            continue
        candidates.append(construction)
    if not candidates:
        return None
    winner = max(candidates, key=lambda item: len(item.normalized_name))
    # Tail is normalized intentionally.  Callers retain their raw PDF source
    # independently; the registry never stores it.
    tail = normalized_object[len(winner.normalized_name):].lstrip(" .,;:-—–")
    return ConstructionMatch(construction=winner, object_tail=tail)
