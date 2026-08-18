"""Pure semantic resolver for construction blocks in an RNS workbook.

This module consumes a small caller-built sheet projection.  It deliberately
does not import openpyxl or the workbook publisher: all returned placement data
is evidence for a later, locking mutation layer, never a mutation instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Iterable

from rns_import_server.normalization import canonical_rns_identity, field_comparison_equal


_FULL_OBJECT_CODE = re.compile(r"^(\d{3}-\d{7})\.\d{4}$")
_EMPTY = (None, "")


class WorkbookGroupCode(StrEnum):
    """Stable, fail-closed results for a requested construction/RNS pair."""

    EXISTING_ROW = "existing_row"
    BLANK_ROW_PLANNED = "blank_row_planned"
    INSERTION_PLANNED = "insertion_planned"
    BLOCK_MISSING = "block_missing"
    BLOCK_DUPLICATE = "block_duplicate"
    BLOCK_CODE_CONFLICT = "block_code_conflict"
    RNS_BLOCK_CONFLICT = "rns_block_conflict"
    RNS_WRONG_BLOCK = "rns_wrong_block"
    INVALID_RNS = "invalid_rns"
    OBJECT_CODE_NAME_CONFLICT = "object_code_name_conflict"
    STALE_WORKBOOK = "stale_workbook"
    STALE_REGISTRY = "stale_registry"
    NO_SAFE_INSERTION_POINT = "no_safe_insertion_point"
    HEADER_CATALOGUE_REQUIRED = "header_catalogue_required"


@dataclass(frozen=True)
class SheetRow:
    """Read-only A:F projection plus explicit template/ownership evidence."""

    number: int
    a: object = None
    b: object = None
    c: object = None
    d: object = None
    e: object = None
    f: object = None
    is_business_row: bool = False
    is_preformatted: bool = False
    group_ownership_proven: bool = False

    @property
    def raw_values(self) -> tuple[object, object, object, object, object, object]:
        return (self.a, self.b, self.c, self.d, self.e, self.f)


@dataclass(frozen=True)
class SheetProjection:
    """Caller-owned workbook identity and an ordered, immutable A:F view."""

    workbook_identity: str
    workbook_hash: str
    registry_generation: int
    rows: tuple[SheetRow, ...]

    @classmethod
    def from_rows(
        cls,
        workbook_identity: str,
        workbook_hash: str,
        registry_generation: int,
        rows: Iterable[SheetRow],
    ) -> "SheetProjection":
        return cls(workbook_identity, workbook_hash, registry_generation, tuple(rows))


@dataclass(frozen=True)
class SemanticRowIdentity:
    """Stable identity; row number and object code are supporting evidence only."""

    construction_id: str
    canonical_rns: str


@dataclass(frozen=True)
class ExistingRow:
    identity: SemanticRowIdentity
    observed_row: int
    raw_values: tuple[object, object, object, object, object, object]


@dataclass(frozen=True)
class MutationPlan:
    """Read-only placement evidence to revalidate immediately before mutation."""

    mode: str
    target_row: int
    workbook_identity: str
    workbook_hash: str
    registry_generation: int
    construction_id: str
    canonical_rns: str


@dataclass(frozen=True)
class WorkbookGroupResolution:
    code: WorkbookGroupCode
    construction_id: str
    official_name: str
    code_prefix: str
    canonical_rns: str | None
    block_start: int | None = None
    block_end: int | None = None
    existing_row: ExistingRow | None = None
    plan: MutationPlan | None = None

    @property
    def is_resolved(self) -> bool:
        return self.code in {
            WorkbookGroupCode.EXISTING_ROW,
            WorkbookGroupCode.BLANK_ROW_PLANNED,
            WorkbookGroupCode.INSERTION_PLANNED,
        }


def _is_blank(value: object) -> bool:
    return value in _EMPTY or (isinstance(value, str) and not value.strip())


def _is_header(row: SheetRow, official_name: str) -> bool:
    return row.d == official_name and all(_is_blank(value) for value in (row.a, row.b, row.c, row.e, row.f))


def _canonical_child_prefix(value: object) -> str | None:
    if not isinstance(value, str) or value in {"", "-"}:
        return None
    match = _FULL_OBJECT_CODE.fullmatch(value)
    return match.group(1) if match else None


def _is_blank_slot(row: SheetRow, *, last_group: bool) -> bool:
    if not (row.is_business_row and row.is_preformatted):
        return False
    if last_group and not row.group_ownership_proven:
        return False
    return all(_is_blank(value) for value in row.raw_values)


def _resolution(
    code: WorkbookGroupCode,
    construction_id: str,
    official_name: str,
    code_prefix: str,
    canonical_rns: str | None,
    **kwargs: object,
) -> WorkbookGroupResolution:
    return WorkbookGroupResolution(code, construction_id, official_name, code_prefix, canonical_rns, **kwargs)


def resolve_workbook_group(
    projection: SheetProjection,
    *,
    construction_id: str,
    official_name: str,
    code_prefix: str,
    rns: object,
    object_code: str | None = None,
    object_name: str | None = None,
    official_names: Iterable[str] | None = None,
    expected_workbook_identity: str | None = None,
    expected_workbook_hash: str | None = None,
    expected_registry_generation: int | None = None,
) -> WorkbookGroupResolution:
    """Resolve one semantic block and return no-op/existing/placement evidence.

    The caller must provide a current projection.  Expected identity values are
    optional optimistic-concurrency guards; a plan always carries actual values
    for the later native publisher to validate again under its publication lock.
    """
    canonical_rns = canonical_rns_identity(rns)
    base = dict(construction_id=construction_id, official_name=official_name, code_prefix=code_prefix, canonical_rns=canonical_rns)
    if expected_workbook_identity is not None and expected_workbook_identity != projection.workbook_identity:
        return _resolution(WorkbookGroupCode.STALE_WORKBOOK, **base)
    if expected_workbook_hash is not None and expected_workbook_hash != projection.workbook_hash:
        return _resolution(WorkbookGroupCode.STALE_WORKBOOK, **base)
    if expected_registry_generation is not None and expected_registry_generation != projection.registry_generation:
        return _resolution(WorkbookGroupCode.STALE_REGISTRY, **base)
    if canonical_rns is None:
        return _resolution(WorkbookGroupCode.INVALID_RNS, **base)

    rows = tuple(sorted(projection.rows, key=lambda row: row.number))
    # A complete immutable catalogue is required to distinguish a real next
    # construction header from ordinary D text.  Guessing it would allow a
    # later block to be swallowed into the current one.
    if official_names is None:
        return _resolution(WorkbookGroupCode.HEADER_CATALOGUE_REQUIRED, **base)
    known_headers = frozenset(name for name in official_names if isinstance(name, str))
    if not known_headers or official_name not in known_headers:
        return _resolution(WorkbookGroupCode.HEADER_CATALOGUE_REQUIRED, **base)
    headers = [index for index, row in enumerate(rows) if _is_header(row, official_name)]
    if not headers:
        return _resolution(WorkbookGroupCode.BLOCK_MISSING, **base)
    if len(headers) != 1:
        return _resolution(WorkbookGroupCode.BLOCK_DUPLICATE, **base)
    header_index = headers[0]
    # A visually blank row with arbitrary D text is not a boundary.  The
    # registry caller injects all official names it considers valid headers.
    next_header_index = next((
        index for index in range(header_index + 1, len(rows))
        if isinstance(rows[index].d, str) and rows[index].d in known_headers and _is_header(rows[index], rows[index].d)
    ), None)
    group_rows = rows[header_index + 1:next_header_index]
    block_start = rows[header_index].number
    block_end = rows[next_header_index].number - 1 if next_header_index is not None else (rows[-1].number if rows else block_start)

    if any((prefix := _canonical_child_prefix(row.c)) is not None and prefix != code_prefix for row in group_rows):
        return _resolution(WorkbookGroupCode.BLOCK_CODE_CONFLICT, **base, block_start=block_start, block_end=block_end)

    if object_code is not None:
        duplicates = [row for row in rows if row.c == object_code]
        if any(not field_comparison_equal("Наименование объекта", str(row.d or ""), object_name) for row in duplicates):
            return _resolution(WorkbookGroupCode.OBJECT_CODE_NAME_CONFLICT, **base, block_start=block_start, block_end=block_end)

    inside = [row for row in group_rows if canonical_rns_identity(row.f) == canonical_rns]
    outside = [row for row in rows if row not in group_rows and canonical_rns_identity(row.f) == canonical_rns]
    if len(inside) > 1:
        return _resolution(WorkbookGroupCode.RNS_BLOCK_CONFLICT, **base, block_start=block_start, block_end=block_end)
    if len(inside) == 1:
        row = inside[0]
        existing = ExistingRow(SemanticRowIdentity(construction_id, canonical_rns), row.number, row.raw_values)
        return _resolution(WorkbookGroupCode.EXISTING_ROW, **base, block_start=block_start, block_end=block_end, existing_row=existing)
    if outside:
        return _resolution(WorkbookGroupCode.RNS_WRONG_BLOCK, **base, block_start=block_start, block_end=block_end)

    last_group = next_header_index is None
    blank = next((row for row in group_rows if _is_blank_slot(row, last_group=last_group)), None)
    if blank is not None:
        plan = MutationPlan("existing_blank", blank.number, projection.workbook_identity, projection.workbook_hash, projection.registry_generation, construction_id, canonical_rns)
        return _resolution(WorkbookGroupCode.BLANK_ROW_PLANNED, **base, block_start=block_start, block_end=block_end, plan=plan)
    if next_header_index is not None:
        target = rows[next_header_index].number
        plan = MutationPlan("insert_before_header", target, projection.workbook_identity, projection.workbook_hash, projection.registry_generation, construction_id, canonical_rns)
        return _resolution(WorkbookGroupCode.INSERTION_PLANNED, **base, block_start=block_start, block_end=block_end, plan=plan)
    return _resolution(WorkbookGroupCode.NO_SAFE_INSERTION_POINT, **base, block_start=block_start, block_end=block_end)
