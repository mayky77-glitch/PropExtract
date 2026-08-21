"""Read-only worksheet-structure oracle for one middle-row insertion."""
from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from .opc_workbook_topology import WorksheetDescriptor
from .opc_worksheet_structure_reader import (
    A1Range,
    WorkbookWorksheetStructureSemantics,
    WorksheetStructuralSemantics,
    read_worksheet_structure_semantics,
)


_MAX_ROW = 1_048_576


__all__ = (
    "OPCWorksheetStructureInsertionOracleError",
    "WorksheetStructureMiddleInsertEvidence",
    "validate_worksheet_structure_middle_insert",
)


@dataclass(frozen=True)
class WorksheetStructureMiddleInsertEvidence:
    """Immutable proof that a target worksheet has one mapped insertion."""

    worksheet: WorksheetDescriptor
    control_dimension: A1Range
    candidate_dimension: A1Range
    insertion_row: int


@dataclass
class OPCWorksheetStructureInsertionOracleError(ValueError):
    """A blocking, stable four-field worksheet-structure mismatch."""

    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetStructureInsertionOracleError(code, subject, field, detail)


def _semantics(
    package: str | Path | PathLike[str], *, sheet_name: str, role: str,
) -> WorkbookWorksheetStructureSemantics:
    try:
        return read_worksheet_structure_semantics(package)
    except OPCWorksheetStructureInsertionOracleError:
        raise
    except Exception as error:
        _fail(
            "invalid-worksheet-structure-insertion-input",
            sheet_name,
            role,
            str(getattr(error, "code", type(error).__name__)),
        )
    raise AssertionError("unreachable")


def _target(
    semantics: WorkbookWorksheetStructureSemantics, *, sheet_name: str, role: str,
) -> WorksheetStructuralSemantics:
    matches = tuple(item for item in semantics.worksheets if item.worksheet.name == sheet_name)
    if len(matches) != 1:
        _fail("ambiguous-worksheet-structure-insertion-sheet", sheet_name, role, str(len(matches)))
    return matches[0]


def _mapped(reference: A1Range, insertion_row: int) -> tuple[int, int, int, int]:
    if reference.max_row < insertion_row:
        return (reference.min_row, reference.min_column, reference.max_row, reference.max_column)
    if reference.min_row >= insertion_row:
        return (reference.min_row + 1, reference.min_column, reference.max_row + 1, reference.max_column)
    return (reference.min_row, reference.min_column, reference.max_row + 1, reference.max_column)


def _geometry(reference: A1Range) -> tuple[int, int, int, int]:
    return (reference.min_row, reference.min_column, reference.max_row, reference.max_column)


def _would_overflow(reference: A1Range, insertion_row: int) -> bool:
    return reference.max_row >= insertion_row and reference.max_row == _MAX_ROW


def _same_workbook_structure(
    control: WorkbookWorksheetStructureSemantics,
    candidate: WorkbookWorksheetStructureSemantics,
    *, sheet_name: str,
) -> None:
    control_descriptors = tuple(item.worksheet for item in control.worksheets)
    candidate_descriptors = tuple(item.worksheet for item in candidate.worksheets)
    if control_descriptors != candidate_descriptors:
        _fail("worksheet-identity-order-mismatch", sheet_name, "worksheets", "identity-or-order")
    for before, after in zip(control.worksheets, candidate.worksheets):
        if before.worksheet.name != sheet_name and before != after:
            _fail("unrelated-worksheet-structure-mismatch", before.worksheet.name, "structure", "changed")


def _mapped_optional(
    before: A1Range | None, after: A1Range | None, *, sheet_name: str, field: str, insertion_row: int,
) -> None:
    if before is None or after is None:
        if before is not after:
            _fail("worksheet-structure-presence-mismatch", sheet_name, field, "missing-or-extra")
        return
    if _mapped(before, insertion_row) != _geometry(after):
        _fail("worksheet-structure-range-mismatch", sheet_name, field, "geometry")


def validate_worksheet_structure_middle_insert(
    control: str | Path | PathLike[str],
    candidate: str | Path | PathLike[str],
    *,
    sheet_name: str,
    insertion_row: int,
) -> WorksheetStructureMiddleInsertEvidence:
    """Block unless worksheet geometry is exactly that of one middle insertion.

    Package access is delegated exclusively to the accepted immutable worksheet
    structure reader; this oracle neither mutates nor saves either package.
    """
    if isinstance(insertion_row, bool) or not isinstance(insertion_row, int) or not 1 <= insertion_row <= _MAX_ROW:
        _fail("invalid-worksheet-structure-insertion-row", str(sheet_name), "insertion_row", str(insertion_row))
    before_all = _semantics(control, sheet_name=sheet_name, role="control")
    after_all = _semantics(candidate, sheet_name=sheet_name, role="candidate")
    _same_workbook_structure(before_all, after_all, sheet_name=sheet_name)
    before = _target(before_all, sheet_name=sheet_name, role="control")
    after = _target(after_all, sheet_name=sheet_name, role="candidate")
    if before.worksheet != after.worksheet:
        _fail("worksheet-identity-order-mismatch", sheet_name, "worksheet", "identity")
    if before.dimension is None or after.dimension is None:
        _fail("worksheet-structure-presence-mismatch", sheet_name, "dimension", "missing-or-extra")
    if not before.dimension.min_row <= insertion_row <= before.dimension.max_row:
        _fail("invalid-worksheet-structure-insertion-row", sheet_name, "insertion_row", str(insertion_row))
    references = (before.dimension, *before.merges)
    if before.auto_filter is not None:
        references += (before.auto_filter.reference,)
    if any(_would_overflow(reference, insertion_row) for reference in references):
        _fail("invalid-worksheet-structure-insertion-row", sheet_name, "insertion_row", str(insertion_row))
    _mapped_optional(before.dimension, after.dimension, sheet_name=sheet_name, field="dimension", insertion_row=insertion_row)
    _mapped_optional(
        before.auto_filter.reference if before.auto_filter else None,
        after.auto_filter.reference if after.auto_filter else None,
        sheet_name=sheet_name,
        field="autoFilter",
        insertion_row=insertion_row,
    )
    if len(before.merges) != len(after.merges):
        _fail("worksheet-structure-count-mismatch", sheet_name, "mergeCells", "count")
    for index, (old, new) in enumerate(zip(before.merges, after.merges)):
        if _mapped(old, insertion_row) != _geometry(new):
            _fail("worksheet-structure-range-mismatch", sheet_name, "mergeCells", str(index))
    return WorksheetStructureMiddleInsertEvidence(before.worksheet, before.dimension, after.dimension, insertion_row)
