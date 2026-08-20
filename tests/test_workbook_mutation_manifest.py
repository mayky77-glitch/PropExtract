from pathlib import Path

import pytest
from openpyxl import Workbook

from rns_import_server.workbook_mutation_manifest import manifest_for, validate_insertion


def _save(path: Path, inserted: bool = False) -> None:
    book = Workbook(); sheet = book.active; sheet.title = "Реестр РНС"
    sheet["A4"] = "1"; sheet["Y4"] = "=A4"; sheet["W4"] = "old"; sheet["W4"].hyperlink = "https://example.test/old"
    if inserted:
        sheet["A5"] = ""; sheet["A6"] = "2"; sheet["Y6"] = "=A6"; sheet["W6"] = "old"; sheet["W6"].hyperlink = "https://example.test/old"
    else:
        sheet["A5"] = "2"; sheet["Y5"] = "=A5"; sheet["W5"] = "old"; sheet["W5"].hyperlink = "https://example.test/old"
    book.save(path); book.close()


def test_manifest_proves_exact_one_insert(tmp_path: Path) -> None:
    control, candidate = tmp_path / "control.xlsx", tmp_path / "candidate.xlsx"; _save(control); _save(candidate, True)
    validate_insertion(manifest_for(control, "Реестр РНС"), manifest_for(candidate, "Реестр РНС", insertion_row=5), 5)


def test_manifest_rejects_unmapped_change(tmp_path: Path) -> None:
    control, candidate = tmp_path / "control.xlsx", tmp_path / "candidate.xlsx"; _save(control); _save(candidate, True)
    from openpyxl import load_workbook
    book = load_workbook(candidate); book.active["Y6"] = "=A1"; book.save(candidate); book.close()
    with pytest.raises(RuntimeError, match="mutation_manifest_changed"):
        validate_insertion(manifest_for(control, "Реестр РНС"), manifest_for(candidate, "Реестр РНС", insertion_row=5), 5)
