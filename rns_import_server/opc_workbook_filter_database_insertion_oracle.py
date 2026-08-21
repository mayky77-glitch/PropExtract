"""Read-only defined-name oracle for one Excel-style middle-row insertion."""
from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from .opc_workbook_defined_name_reader import (
    WorkbookDefinedNameSemantics,
    WorkbookFilterDatabase,
    read_workbook_defined_name_semantics,
)
from .opc_workbook_topology import WorksheetDescriptor
from .opc_worksheet_structure_reader import A1Range


__all__ = (
    "FilterDatabaseMiddleInsertEvidence",
    "OPCWorkbookFilterDatabaseInsertionOracleError",
    "validate_filter_database_middle_insert",
)


_FILTER_DATABASE = "_xlnm._FilterDatabase"


@dataclass(frozen=True)
class FilterDatabaseMiddleInsertEvidence:
    """Immutable semantic proof for the accepted target FilterDatabase."""

    worksheet: WorksheetDescriptor
    control_reference: A1Range
    candidate_reference: A1Range
    insertion_row: int


@dataclass
class OPCWorkbookFilterDatabaseInsertionOracleError(ValueError):
    """A blocking, stable four-field defined-name insertion mismatch."""

    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorkbookFilterDatabaseInsertionOracleError(code, subject, field, detail)


def _semantics(path: str | PathLike[str], *, sheet_name: str, role: str) -> WorkbookDefinedNameSemantics:
    """Use the accepted reader as the sole defined-name/package boundary."""
    try:
        return read_workbook_defined_name_semantics(path)
    except Exception as error:
        code = getattr(error, "code", type(error).__name__)
        if code == "duplicate-filter-database-scope":
            _fail("ambiguous-filter-database-owner", sheet_name, "owner_count", "multiple")
        _fail("invalid-filter-database-insertion-input", sheet_name, role, str(code))
    raise AssertionError("unreachable")


def _target_owner(
    semantics: WorkbookDefinedNameSemantics, *, sheet_name: str,
) -> WorkbookFilterDatabase:
    owners = tuple(item for item in semantics.filter_databases if item.worksheet.name == sheet_name)
    if not owners:
        _fail("missing-filter-database-owner", sheet_name, "owner_count", "0")
    if len(owners) != 1:
        _fail("ambiguous-filter-database-owner", sheet_name, "owner_count", str(len(owners)))
    return owners[0]


def _target_index(semantics: WorkbookDefinedNameSemantics, owner: WorkbookFilterDatabase) -> int:
    filter_records = tuple(
        index for index, name in enumerate(semantics.defined_names)
        if name.name == _FILTER_DATABASE
    )
    indexes = tuple(index for index, database in zip(filter_records, semantics.filter_databases) if database == owner)
    if len(indexes) != 1:
        _fail("ambiguous-filter-database-owner", owner.worksheet.name, "owner_count", str(len(indexes)))
    return indexes[0]


def _preserved_names(
    control: WorkbookDefinedNameSemantics,
    candidate: WorkbookDefinedNameSemantics,
    *, control_owner: WorkbookFilterDatabase,
    candidate_owner: WorkbookFilterDatabase,
) -> None:
    """Permit only semantic spelling changes to the target range expression."""
    if len(control.defined_names) != len(candidate.defined_names):
        _fail("defined-name-order-mismatch", control_owner.worksheet.name, "defined_names", "count")
    control_index = _target_index(control, control_owner)
    candidate_index = _target_index(candidate, candidate_owner)
    if control_index != candidate_index:
        _fail("defined-name-order-mismatch", control_owner.worksheet.name, "defined_names", "filter_database")
    for index, (before, after) in enumerate(zip(control.defined_names, candidate.defined_names)):
        if (before.name, before.local_sheet_index, before.hidden) != (after.name, after.local_sheet_index, after.hidden):
            _fail("defined-name-metadata-mismatch", control_owner.worksheet.name, "defined_name", str(index))
        if index != control_index and before != after:
            _fail("defined-name-expression-mismatch", control_owner.worksheet.name, "defined_name", str(index))


def validate_filter_database_middle_insert(
    control: str | Path | PathLike[str],
    candidate: str | Path | PathLike[str],
    *,
    sheet_name: str,
    insertion_row: int,
) -> FilterDatabaseMiddleInsertEvidence:
    """Block unless exactly one target FilterDatabase expands by one final row.

    This function reads only through the accepted defined-name reader.  Its
    comparison intentionally ignores raw formula spelling for the target range,
    while preserving every other defined-name record exactly.
    """
    if isinstance(insertion_row, bool) or not isinstance(insertion_row, int):
        _fail("invalid-filter-database-insertion-row", str(sheet_name), "insertion_row", type(insertion_row).__name__)
    control_names = _semantics(control, sheet_name=sheet_name, role="control")
    candidate_names = _semantics(candidate, sheet_name=sheet_name, role="candidate")
    control_owner = _target_owner(control_names, sheet_name=sheet_name)
    candidate_owner = _target_owner(candidate_names, sheet_name=sheet_name)

    if control_owner.worksheet != candidate_owner.worksheet:
        _fail("filter-database-worksheet-mismatch", sheet_name, "worksheet", "identity")
    _preserved_names(
        control_names,
        candidate_names,
        control_owner=control_owner,
        candidate_owner=candidate_owner,
    )
    before, after = control_owner.reference, candidate_owner.reference
    if insertion_row <= before.min_row or insertion_row > before.max_row:
        _fail("invalid-filter-database-insertion-row", sheet_name, "insertion_row", str(insertion_row))
    if (before.min_column, before.max_column, before.min_row) != (after.min_column, after.max_column, after.min_row):
        _fail("filter-database-range-mismatch", sheet_name, "range", "columns-or-first-row")
    if after.max_row != before.max_row + 1:
        _fail("filter-database-range-mismatch", sheet_name, "range", "last-row")
    return FilterDatabaseMiddleInsertEvidence(control_owner.worksheet, before, after, insertion_row)
