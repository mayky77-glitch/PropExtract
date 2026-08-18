"""Deterministic, read-only semantic manifests for paired Excel outputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    digest: str


def manifest_for(path: Path, sheet_name: str, *, insertion_row: int | None = None) -> MutationManifest:
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        sheet = book[sheet_name]
        values: dict[str, object] = {}
        formulas: dict[str, str] = {}
        links: dict[str, str] = {}
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value not in (None, ""):
                    (formulas if isinstance(cell.value, str) and cell.value.startswith("=") else values)[cell.coordinate] = cell.value
                hyperlink = getattr(cell, "hyperlink", None)
                if hyperlink and hyperlink.target:
                    links[cell.coordinate] = hyperlink.target
        payload = {"version": "native-group-row-insertion-v1", "sheet": sheet_name, "insertion_row": insertion_row,
                   "max_row": sheet.max_row, "values": values, "formulas": formulas, "hyperlinks": links}
        return MutationManifest(**payload, digest=digest(payload))
    finally:
        book.close()


def validate_insertion(control: MutationManifest, candidate: MutationManifest, row: int) -> None:
    """Prove exactly one physical row and forbid edits outside the mapped insert."""
    if control.sheet != candidate.sheet or candidate.max_row != control.max_row + 1:
        raise RuntimeError("mutation_manifest_row_count_mismatch")
    if row < 1:
        raise RuntimeError("mutation_manifest_insert_row_invalid")
    for source, target in ((control.values, candidate.values), (control.formulas, candidate.formulas), (control.hyperlinks, candidate.hyperlinks)):
        for coordinate, value in source.items():
            from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
            column, source_row = coordinate_from_string(coordinate)
            mapped = f"{column}{source_row if source_row < row else source_row + 1}"
            expected = value
            if source is control.formulas:
                from openpyxl.formula.translate import Translator
                expected = Translator(value, origin=coordinate).translate_formula(mapped)
            if target.get(mapped) != expected and not (column == "A" and source_row >= row):
                raise RuntimeError(f"mutation_manifest_changed:{coordinate}")
