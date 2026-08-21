from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook, load_workbook

import rns_import_server.group_row_insertion as insertion
from rns_import_server.audit import sha256
from rns_import_server.group_row_insertion import GroupRowInsertionError, GroupRowRequest, PublicationContext, publish_group_row, recover_group_row
from rns_import_server.opc_worksheet_x14_cf_insertion_oracle import OPCWorksheetX14CfInsertionOracleError
from rns_import_server.opc_workbook_filter_database_insertion_oracle import OPCWorkbookFilterDatabaseInsertionOracleError
from rns_import_server.opc_worksheet_structure_insertion_oracle import OPCWorksheetStructureInsertionOracleError
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


def _patch_middle_insert_pre_oracle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(insertion, "insertion_is_structurally_safe", lambda *_: True)
    monkeypatch.setattr(insertion, "manifest_for", lambda *_args, **_kwargs: SimpleNamespace(digest="manifest"))
    monkeypatch.setattr(insertion, "validate_control", lambda *_: None)
    monkeypatch.setattr(insertion, "validate_insertion", lambda *_: None)
    monkeypatch.setattr(insertion, "validate_filter_database_middle_insert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(insertion, "validate_worksheet_structure_middle_insert", lambda *_args, **_kwargs: None)


def test_middle_insert_calls_x14_oracle_after_generic_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    plan = MutationPlan("insert_before_header", 6, "book", sha256(source), 1, "construction", "RU-00000000-00-2026")
    journal = Journal(); _patch_middle_insert_pre_oracle(monkeypatch)
    calls = []
    monkeypatch.setattr(insertion, "validate_x14_cf_middle_insert", lambda *args, **kwargs: calls.append((args, kwargs)))
    result = publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {6: plan.canonical_rns}, context=_context(plan, journal)), native_script=tmp_path / "helper.ps1", operation_directory=tmp_path / "ops")
    assert result["published"] is True and output.exists()
    assert len(calls) == 1
    (control, candidate), kwargs = calls[0]
    assert (control.name, candidate.name, control.parent == candidate.parent) == ("control.xlsx", "candidate.xlsx", True)
    assert kwargs == {"sheet_name": "Реестр РНС", "insertion_row": 6, "format_source_row": 5}


def test_middle_insert_x14_oracle_failure_blocks_publication_and_requests_manual_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    source_hash = sha256(source)
    plan = MutationPlan("insert_before_header", 6, "book", source_hash, 1, "construction", "RU-00000000-00-2026")
    journal = Journal(); _patch_middle_insert_pre_oracle(monkeypatch)
    failure = OPCWorksheetX14CfInsertionOracleError("x14-cf-sqref-mismatch", "Реестр РНС", "sqref", "rule")
    monkeypatch.setattr(insertion, "validate_x14_cf_middle_insert", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(GroupRowInsertionError) as captured:
        publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {6: plan.canonical_rns}, context=_context(plan, journal)), native_script=tmp_path / "helper.ps1", operation_directory=tmp_path / "ops")
    assert (captured.value.code, captured.value.stage, captured.value.cause) == (failure.code, "validate", failure)
    assert sha256(source) == source_hash and not output.exists()
    assert not list((tmp_path / "ops").rglob("backup.xlsx"))
    assert "published" not in [name for name, _ in journal.calls] and journal.calls[-1][0] == "manual_repair"


def test_middle_insert_filter_database_oracle_failure_after_x14_blocks_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    source_hash = sha256(source)
    plan = MutationPlan("insert_before_header", 6, "book", source_hash, 1, "construction", "RU-00000000-00-2026")
    journal = Journal(); _patch_middle_insert_pre_oracle(monkeypatch)
    calls = []
    monkeypatch.setattr(insertion, "validate_x14_cf_middle_insert", lambda *_args, **_kwargs: calls.append("x14"))
    failure = OPCWorkbookFilterDatabaseInsertionOracleError("filter-database-range-mismatch", "Реестр РНС", "range", "last-row")
    monkeypatch.setattr(insertion, "validate_filter_database_middle_insert", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(GroupRowInsertionError) as captured:
        publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {6: plan.canonical_rns}, context=_context(plan, journal)), native_script=tmp_path / "helper.ps1", operation_directory=tmp_path / "ops")
    assert (captured.value.code, captured.value.stage, captured.value.cause) == (failure.code, "validate", failure)
    assert calls == ["x14"]
    assert sha256(source) == source_hash and not output.exists()
    assert not list((tmp_path / "ops").rglob("backup.xlsx"))
    assert "published" not in [name for name, _ in journal.calls] and journal.calls[-1][0] == "manual_repair"


def test_middle_insert_structure_oracle_runs_after_x14_and_filter_and_blocks_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "out.xlsx"; _book(source)
    source_hash = sha256(source)
    plan = MutationPlan("insert_before_header", 6, "book", source_hash, 1, "construction", "RU-00000000-00-2026")
    journal = Journal(); _patch_middle_insert_pre_oracle(monkeypatch)
    calls = []
    monkeypatch.setattr(insertion, "validate_x14_cf_middle_insert", lambda *_args, **_kwargs: calls.append("x14"))
    monkeypatch.setattr(insertion, "validate_filter_database_middle_insert", lambda *_args, **_kwargs: calls.append("filter"))
    failure = OPCWorksheetStructureInsertionOracleError("worksheet-structure-range-mismatch", "Реестр РНС", "dimension", "geometry")
    monkeypatch.setattr(insertion, "validate_worksheet_structure_middle_insert", lambda *_args, **_kwargs: calls.append("structure") or (_ for _ in ()).throw(failure))
    with pytest.raises(GroupRowInsertionError) as captured:
        publish_group_row(GroupRowRequest(plan, source, output, "Реестр РНС", {6: plan.canonical_rns}, context=_context(plan, journal)), native_script=tmp_path / "helper.ps1", operation_directory=tmp_path / "ops")
    assert (captured.value.code, captured.value.stage, captured.value.cause) == (failure.code, "validate", failure)
    assert calls == ["x14", "filter", "structure"]
    assert sha256(source) == source_hash and not output.exists() and not list((tmp_path / "ops").rglob("backup.xlsx"))


def test_third_hash_recovery_is_manual_repair(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"; _book(source); journal = Journal()
    journal.phase = "staged"; context = PublicationContext(lambda: nullcontext(), lambda current: current, journal, 1, "book")
    assert recover_group_row(context=context, operation={"operation_id": "op", "phase": "staged", "pre_hash": "old", "post_hash": "new"}, source=source) == "manual_repair"
    assert journal.calls[-1][0] == "manual_repair"
