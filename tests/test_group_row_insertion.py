from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from rns_import_server.audit import sha256
from rns_import_server.group_row_insertion import GroupRowInsertionError, GroupRowRequest, publish_group_row
from rns_import_server.workbook_groups import MutationPlan


def _book(path: Path) -> None:
    book = Workbook(); sheet = book.active; sheet.title = "Реестр РНС"
    sheet.cell(4, 4).value = "Группа"; sheet.cell(5, 1).value = None; sheet.cell(5, 2).value = None
    book.save(path); book.close()


def test_proven_blank_fill_publishes_without_a_shift(tmp_path: Path) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    plan = MutationPlan("existing_blank", 5, "book", sha256(source), 1, "construction", "RU-00000000-00-2026")
    result = publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {6: plan.canonical_rns}), native_script=tmp_path / "missing.ps1", operation_directory=tmp_path / "op")
    assert result == {"mode": "blank_fill", "row": 5, "published": True}
    assert load_workbook(output, read_only=True)["Реестр РНС"].cell(5, 6).value == plan.canonical_rns


@pytest.mark.parametrize("header", [6, 10, 104])
def test_middle_insert_requires_excel_and_preserves_source(tmp_path: Path, header: int) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    plan = MutationPlan("insert_before_header", header, "book", sha256(source), 1, "construction", "RU-00000000-00-2026")
    before = source.read_bytes()
    with pytest.raises(GroupRowInsertionError, match="excel_required_for_middle_insert"):
        publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {6: plan.canonical_rns}), native_script=tmp_path / "missing.ps1", operation_directory=tmp_path / "op")
    assert source.read_bytes() == before and not output.exists()
