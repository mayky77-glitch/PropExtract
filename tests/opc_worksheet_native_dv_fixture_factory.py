"""Direct ZIP/XML fixtures for worksheet native-data-validation semantics."""
from __future__ import annotations

from pathlib import Path

from tests.opc_worksheet_cell_fixture_factory import package as _package

SML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XR = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
X14 = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"


def worksheet(validations: str = "") -> bytes:
    return f'<worksheet xmlns="{SML}" xmlns:xr="{XR}" xmlns:x14="{X14}">{validations}</worksheet>'.encode()


def package(destination: Path, *, sheet_one: bytes | None = None, sheet_two: bytes | None = None,
            sheet_one_name: str = "xl/worksheets/first.xml", extra_members: tuple[tuple[str, bytes], ...] = ()) -> Path:
    return _package(destination, sheet_one=sheet_one or worksheet(), sheet_two=sheet_two or worksheet(),
                    sheet_one_name=sheet_one_name, extra_members=extra_members)
