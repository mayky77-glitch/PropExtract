from pathlib import Path

from openpyxl import Workbook

from rns_import_server.workbook_structure import insertion_is_structurally_safe, inspect_workbook


def test_preflight_rejects_vertical_merge_split(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"; book = Workbook(); book.active.title = "Реестр РНС"; book.active.merge_cells("A4:A6"); book.save(path); book.close()
    structure = inspect_workbook(path, "Реестр РНС")
    assert not insertion_is_structurally_safe(structure, 5)
