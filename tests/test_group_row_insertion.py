from contextlib import nullcontext
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from rns_import_server.audit import sha256
from rns_import_server.group_row_insertion import GroupRowInsertionError, GroupRowRequest, PublicationContext, publish_group_row, recover_group_row
from rns_import_server.workbook_groups import MutationPlan


class Journal:
    def __init__(self): self.calls = []; self.phase = "planned"
    def create(self, **kwargs): self.calls.append(("create", kwargs)); return object()
    def transition(self, operation_id, *, expected_phase, next_phase, **kwargs):
        assert self.phase == expected_phase; self.phase = next_phase; self.calls.append((next_phase, kwargs)); return object()
    def record_post_hash(self, operation_id, *, expected_phase, post_hash):
        assert self.phase == expected_phase; self.calls.append(("post", post_hash)); return object()
    def finalize_flag(self, operation_id, flag): self.calls.append((flag, {})); return object()


def _book(path: Path) -> None:
    book = Workbook(); sheet = book.active; sheet.title = "Реестр РНС"; sheet.cell(5, 1).value = None; book.save(path); book.close()


def _context(plan, journal):
    def native(request, _script):
        book = load_workbook(request.candidate); book[request.sheet].cell(request.insertion_row, 6).value = plan.canonical_rns; book.save(request.candidate); book.close()
        return {"lease": {"excel_adapter": "mock", "excel_pid": 1, "excel_hwnd": 2, "excel_process_started_at": "now", "excel_build": "mock"}}
    return PublicationContext(lambda: nullcontext(), lambda current: current, journal, plan.registry_generation, plan.workbook_identity, native_runner=native)


def test_blank_fill_requires_context() -> None:
    plan = MutationPlan("existing_blank", 5, "book", "hash", 1, "construction", "RU-00000000-00-2026")
    with pytest.raises(GroupRowInsertionError, match="publication_context_required"):
        publish_group_row(GroupRowRequest(plan, Path("source"), Path("out"), "Реестр РНС", {}), native_script=Path("x"), operation_directory=Path("ops"))


def test_mocked_blank_lifecycle_is_locked_journaled_and_published(tmp_path: Path) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    plan = MutationPlan("existing_blank", 5, "book", sha256(source), 1, "construction", "RU-00000000-00-2026")
    journal = Journal(); result = publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {6: plan.canonical_rns}, context=_context(plan, journal)), native_script=tmp_path / "helper.ps1", operation_directory=tmp_path / "ops")
    assert result["published"] is True and load_workbook(output, read_only=True)["Реестр РНС"].cell(5, 6).value == plan.canonical_rns
    assert [name for name, _ in journal.calls if name in {"staged", "native", "validated", "backup_verified", "published", "finalized"}] == ["staged", "native", "validated", "backup_verified", "published", "finalized"]


@pytest.mark.parametrize("header", [6, 10, 104])
def test_middle_insert_no_excel_is_typed_prepublication_failure(tmp_path: Path, header: int) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    plan = MutationPlan("insert_before_header", header, "book", sha256(source), 1, "construction", "RU-00000000-00-2026")
    journal = Journal(); context = PublicationContext(lambda: nullcontext(), lambda current: current, journal, 1, "book")
    with pytest.raises(GroupRowInsertionError, match="excel_required_for_middle_insert"):
        publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {}, context=context), native_script=tmp_path / "helper.ps1", operation_directory=tmp_path / "ops")
    assert source.exists() and not output.exists()


def test_third_hash_recovery_is_manual_repair(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"; _book(source); journal = Journal()
    journal.phase = "staged"; context = PublicationContext(lambda: nullcontext(), lambda current: current, journal, 1, "book")
    assert recover_group_row(context=context, operation={"operation_id": "op", "phase": "staged", "pre_hash": "old", "post_hash": "new"}, source=source) == "manual_repair"
    assert journal.calls[-1][0] == "manual_repair"
