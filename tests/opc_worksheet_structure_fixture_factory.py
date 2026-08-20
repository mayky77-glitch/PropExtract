"""Direct ZIP/XML fixtures for strict worksheet structure semantics."""
from __future__ import annotations
from pathlib import Path
from tests.opc_worksheet_cell_fixture_factory import package as _package

SML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

def worksheet(*, dimension: str = '<dimension ref="A6:C104"/>', rows: str = '<row r="6"><c r="A6"><v>1</v></c></row><row r="10"><c r="B10"><v>2</v></c></row><row r="104"><c r="C104"><v>3</v></c></row>', auto_filter: str = '<autoFilter ref="A6:C104"/>', merges: str = '<mergeCells count="2"><mergeCell ref="A6:B6"/><mergeCell ref="A10:C104"/></mergeCells>') -> bytes:
    return f'<worksheet xmlns="{SML}">{dimension}<sheetData>{rows}</sheetData>{auto_filter}{merges}</worksheet>'.encode()

def package(destination: Path, *, sheet_one: bytes | None = None, sheet_two: bytes | None = None, sheet_one_name: str = "xl/worksheets/first.xml", extra_members: tuple[tuple[str, bytes], ...] = ()) -> Path:
    return _package(destination, sheet_one=sheet_one or worksheet(), sheet_two=sheet_two or worksheet(dimension="", auto_filter="", merges=""), sheet_one_name=sheet_one_name, extra_members=extra_members)
