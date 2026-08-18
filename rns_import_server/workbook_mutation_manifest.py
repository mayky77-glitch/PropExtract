"""Deterministic, read-only semantic manifests for paired Excel outputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile

from openpyxl import load_workbook

from rns_import_server.audit import digest


ALLOWLISTED_COLUMNS = tuple(range(1, 25)) + (27,)  # A:X and AA


@dataclass(frozen=True)
class MutationManifest:
    version: str
    sheet: str
    insertion_row: int | None
    max_row: int
    values: dict[str, object]
    formulas: dict[str, str]
    hyperlinks: dict[str, str]
    styles: dict[str, int]
    structure: tuple[object, ...]
    package_fingerprint: str
    digest: str


@dataclass(frozen=True)
class InsertionExpectation:
    values: dict[str, object]
    formulas: dict[str, str]
    hyperlink_target: str
    hyperlink_display: str
    ordinal: object


def manifest_for(path: Path, sheet_name: str, *, insertion_row: int | None = None) -> MutationManifest:
    book = load_workbook(path, read_only=False, data_only=False)
    try:
        sheet = book[sheet_name]
        values: dict[str, object] = {}
        formulas: dict[str, str] = {}
        links: dict[str, str] = {}
        styles: dict[str, int] = {}
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value not in (None, ""):
                    (formulas if isinstance(cell.value, str) and cell.value.startswith("=") else values)[cell.coordinate] = cell.value
                hyperlink = getattr(cell, "hyperlink", None)
                if hyperlink and hyperlink.target:
                    links[cell.coordinate] = hyperlink.target
                if getattr(cell, "style_id", 0): styles[cell.coordinate] = cell.style_id
        structure = (sheet.auto_filter.ref, tuple(sorted(str(item) for item in sheet.merged_cells.ranges)),
                     tuple(sorted(item.name for item in book.defined_names.values())),
                     tuple(sorted(str(item.sqref) for item in sheet.data_validations.dataValidation)),
                     tuple(sorted(str(item.sqref) for item in sheet.conditional_formatting)))
        with zipfile.ZipFile(path) as archive:
            package = {name: digest(archive.read(name).decode("utf-8", "replace")) for name in sorted(archive.namelist()) if name.startswith(("xl/worksheets/", "xl/workbook.xml", "xl/styles", "xl/worksheets/_rels/"))}
        payload = {"version": "native-group-row-insertion-v1", "sheet": sheet_name, "insertion_row": insertion_row,
                   "max_row": sheet.max_row, "values": values, "formulas": formulas, "hyperlinks": links, "styles": styles, "structure": structure}
        return MutationManifest(**payload, package_fingerprint=digest(package), digest=digest(payload))
    finally:
        book.close()


def validate_insertion(control: MutationManifest, candidate: MutationManifest, row: int, *, expected: InsertionExpectation | None = None) -> None:
    """Prove exactly one physical row and forbid edits outside the mapped insert."""
    if control.sheet != candidate.sheet or candidate.max_row != control.max_row + 1:
        raise RuntimeError("mutation_manifest_row_count_mismatch")
    if row < 1:
        raise RuntimeError("mutation_manifest_insert_row_invalid")
    for source, target in ((control.values, candidate.values), (control.formulas, candidate.formulas), (control.hyperlinks, candidate.hyperlinks), (control.styles, candidate.styles)):
        for coordinate, value in source.items():
            from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
            column, source_row = coordinate_from_string(coordinate)
            mapped = f"{column}{source_row if source_row < row else source_row + 1}"
            expected_value = value
            if source is control.formulas:
                from openpyxl.formula.translate import Translator
                expected_value = Translator(value, origin=coordinate).translate_formula(mapped)
            if target.get(mapped) != expected_value and not (column == "A" and source_row >= row):
                raise RuntimeError(f"mutation_manifest_changed:{coordinate}")
        for coordinate in target:
            from openpyxl.utils.cell import coordinate_from_string
            column, target_row = coordinate_from_string(coordinate)
            if target_row == row:
                if column not in {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA"}:
                    raise RuntimeError(f"mutation_manifest_inserted_not_allowed:{coordinate}")
                continue
            source_row = target_row if target_row < row else target_row - 1
            if f"{column}{source_row}" not in source:
                raise RuntimeError(f"mutation_manifest_candidate_only:{coordinate}")
    if control.structure != candidate.structure:
        raise RuntimeError("mutation_manifest_structure_changed")
    if expected:
        for column, value in expected.values.items():
            if candidate.values.get(f"{column}{row}") != value: raise RuntimeError(f"mutation_manifest_insert_value:{column}")
        for column, value in expected.formulas.items():
            if candidate.formulas.get(f"{column}{row}") != value: raise RuntimeError(f"mutation_manifest_insert_formula:{column}")
        if candidate.values.get(f"A{row}") != expected.ordinal: raise RuntimeError("mutation_manifest_insert_ordinal")
        if candidate.hyperlinks.get(f"W{row}") != expected.hyperlink_target or candidate.values.get(f"W{row}") != expected.hyperlink_display:
            raise RuntimeError("mutation_manifest_insert_hyperlink")


def validate_control(original: MutationManifest, control: MutationManifest) -> None:
    """A control can normalize caches, but cannot change semantic workbook data."""
    if original.sheet != control.sheet or original.max_row != control.max_row:
        raise RuntimeError("control_manifest_structure_changed")
    if (original.values != control.values or original.formulas != control.formulas or original.hyperlinks != control.hyperlinks
            or original.styles != control.styles or original.structure != control.structure):
        raise RuntimeError("control_manifest_semantic_changed")
