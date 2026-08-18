"""Pure, fail-closed construction routing for raw PDF object names.

The router consumes a caller-supplied immutable registry projection.  It never
opens the SQLite registry and deliberately knows nothing about workbook rows or
placement.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import unicodedata
from typing import Iterable

from rns_import_server.construction_registry import Construction, STATUSES
from rns_import_server.normalization import normalize_text


class ObjectRouteCode(StrEnum):
    """Stable result codes for object-to-construction routing."""

    ROUTED = "routed"
    UNKNOWN_CONSTRUCTION = "unknown_construction"
    EMPTY_OBJECT_TAIL = "empty_object_tail"
    CONFLICTING_SNAPSHOT = "conflicting_snapshot"
    STALE_REGISTRY = "stale_registry"
    DRAFT_NOT_ROUTABLE = "draft_not_routable"
    ARCHIVED_FOR_NEW_ROW = "archived_for_new_row"
    ARCHIVED_EXISTING_ONLY = "archived_existing_only"


@dataclass(frozen=True)
class ConstructionRegistrySnapshot:
    """Read-only routing input supplied by the registry/API boundary."""

    generation: int
    constructions: tuple[Construction, ...]

    @classmethod
    def from_constructions(
        cls, generation: int, constructions: Iterable[Construction]
    ) -> "ConstructionRegistrySnapshot":
        return cls(generation=generation, constructions=tuple(constructions))


@dataclass(frozen=True)
class ObjectRoute:
    """Transport-neutral route outcome; raw source text is never modified."""

    code: ObjectRouteCode
    registry_generation: int
    raw_object: str | None
    object_tail: str | None = None
    construction_id: str | None = None
    code_prefix: str | None = None
    construction_status: str | None = None
    can_create_new_row: bool = False

    @property
    def is_routable(self) -> bool:
        return self.code is ObjectRouteCode.ROUTED


_BOUNDARY_CHARS = frozenset(".,;:!?)]}>»\"'/\\-—–")
def _normalized_with_raw_offsets(value: str) -> tuple[str, tuple[int, ...]]:
    """Return registry-compatible normalized text and raw end offsets.

    Offsets make it possible to compare normalized Unicode safely while still
    returning the tail from the original raw source, including its casing.
    """
    normalized = ""
    offsets: list[int] = []
    for raw_index in range(1, len(value) + 1):
        # Normalize each complete prefix.  NFKC may compose a character with a
        # following combining mark, so normalizing character-by-character
        # cannot match an official precomposed name such as ``Йод``.
        updated = normalize_text(value[:raw_index]) or ""
        unchanged = 0
        for previous, current in zip(normalized, updated):
            if previous != current:
                break
            unchanged += 1
        offsets[unchanged:] = [raw_index] * (len(updated) - unchanged)
        normalized = updated
    return normalized, tuple(offsets)


def _snapshot_conflicts(snapshot: ConstructionRegistrySnapshot) -> bool:
    if not isinstance(snapshot.generation, int) or isinstance(snapshot.generation, bool) or snapshot.generation < 0:
        return True
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    seen_codes: set[str] = set()
    for construction in snapshot.constructions:
        if not isinstance(construction, Construction) or construction.status not in STATUSES:
            return True
        normalized_name = normalize_text(construction.official_name)
        if not normalized_name or normalized_name != construction.normalized_name:
            return True
        if (construction.id in seen_ids or normalized_name in seen_names or construction.code_prefix in seen_codes):
            return True
        seen_ids.add(construction.id)
        seen_names.add(normalized_name)
        seen_codes.add(construction.code_prefix)
    return False


def _matched_construction(normalized_object: str, constructions: Iterable[Construction]) -> Construction | None:
    candidates: list[Construction] = []
    for construction in constructions:
        if not normalized_object.startswith(construction.normalized_name):
            continue
        remainder = normalized_object[len(construction.normalized_name):]
        if remainder and not (remainder[0].isspace() or remainder[0] in _BOUNDARY_CHARS):
            continue
        candidates.append(construction)
    return max(candidates, key=lambda item: len(item.normalized_name), default=None)


def _raw_tail(raw_object: str, offsets: tuple[int, ...], prefix_length: int) -> str:
    """Return raw tail after one validated separator, without over-stripping."""
    tail = raw_object[offsets[prefix_length - 1]:]
    position = 0

    while position < len(tail) and tail[position].isspace():
        position += 1
    if position < len(tail) and unicodedata.normalize("NFKC", tail[position]) in _BOUNDARY_CHARS:
        position += 1
        while position < len(tail) and tail[position].isspace():
            position += 1
    return tail[position:]


def _outcome_for(construction: Construction, snapshot: ConstructionRegistrySnapshot, raw_object: str | None, *,
                 code: ObjectRouteCode, object_tail: str | None = None, can_create_new_row: bool = False) -> ObjectRoute:
    return ObjectRoute(
        code=code,
        registry_generation=snapshot.generation,
        raw_object=raw_object,
        object_tail=object_tail,
        construction_id=construction.id,
        code_prefix=construction.code_prefix,
        construction_status=construction.status,
        can_create_new_row=can_create_new_row,
    )


def route_object(
    raw_object: str | None,
    snapshot: ConstructionRegistrySnapshot,
    *,
    expected_generation: int | None = None,
    existing_construction_id: str | None = None,
) -> ObjectRoute:
    """Route a raw object name using only an immutable registry snapshot.

    ``existing_construction_id`` is comparison context only.  It never permits
    a new row for an archived construction.
    """
    if expected_generation is not None and expected_generation != snapshot.generation:
        return ObjectRoute(ObjectRouteCode.STALE_REGISTRY, snapshot.generation, raw_object)
    if _snapshot_conflicts(snapshot):
        return ObjectRoute(ObjectRouteCode.CONFLICTING_SNAPSHOT, snapshot.generation, raw_object)
    if not isinstance(raw_object, str):
        return ObjectRoute(ObjectRouteCode.UNKNOWN_CONSTRUCTION, snapshot.generation, raw_object)

    normalized_object, offsets = _normalized_with_raw_offsets(raw_object)
    if not normalized_object:
        return ObjectRoute(ObjectRouteCode.UNKNOWN_CONSTRUCTION, snapshot.generation, raw_object)
    construction = _matched_construction(normalized_object, snapshot.constructions)
    if construction is None:
        return ObjectRoute(ObjectRouteCode.UNKNOWN_CONSTRUCTION, snapshot.generation, raw_object)
    tail = _raw_tail(raw_object, offsets, len(construction.normalized_name))
    if not tail:
        return _outcome_for(construction, snapshot, raw_object, code=ObjectRouteCode.EMPTY_OBJECT_TAIL)
    if construction.status == "draft":
        return _outcome_for(construction, snapshot, raw_object, code=ObjectRouteCode.DRAFT_NOT_ROUTABLE, object_tail=tail)
    if construction.status == "archived":
        code = (ObjectRouteCode.ARCHIVED_EXISTING_ONLY if existing_construction_id == construction.id
                else ObjectRouteCode.ARCHIVED_FOR_NEW_ROW)
        return _outcome_for(construction, snapshot, raw_object, code=code, object_tail=tail)
    return _outcome_for(
        construction, snapshot, raw_object, code=ObjectRouteCode.ROUTED,
        object_tail=tail, can_create_new_row=True,
    )
