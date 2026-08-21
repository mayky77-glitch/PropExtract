"""Bounded read-only contract for FilterDatabase middle-row insertion."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from rns_import_server.opc_workbook_filter_database_insertion_oracle import (
    OPCWorkbookFilterDatabaseInsertionOracleError,
    validate_filter_database_middle_insert,
)
from rns_import_server.opc_workbook_defined_name_reader import read_workbook_defined_name_semantics
from tests.opc_workbook_defined_name_fixture_factory import package, workbook


SHEET = "Первый"
FILTER = '<definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!$a$3:$aq$605</definedName>'


def _book(path: Path, names: str) -> Path:
    return package(path, workbook_xml=workbook(f"<definedNames>{names}</definedNames>"))


@pytest.mark.parametrize("row", (6, 10, 104))
def test_rows_accept_semantic_a3_aq605_to_a3_aq606_and_real_source_is_read_only(tmp_path: Path, row: int) -> None:
    control = _book(tmp_path / f"control-{row}.xlsx", FILTER)
    candidate = _book(
        tmp_path / f"candidate-{row}.xlsx",
        '<definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A3:AQ606</definedName>',
    )
    evidence = validate_filter_database_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=row)
    assert (evidence.control_reference.start, evidence.control_reference.end, evidence.candidate_reference.end) == (
        "A3", "AQ605", "AQ606",
    )

    source = Path(__file__).resolve().parents[4] / "Автоматизация РнС и ГРО" / "Реестр РНС Иркутск.xlsx"
    before = sha256(source.read_bytes()).hexdigest()
    owners = tuple(item for item in read_workbook_defined_name_semantics(source).filter_databases if item.worksheet.name == "Реестр РНС")
    assert len(owners) == 1
    assert (owners[0].reference.start, owners[0].reference.end) == ("A3", "AQ605")
    assert owners[0].reference.min_row < row <= owners[0].reference.max_row
    assert sha256(source.read_bytes()).hexdigest() == before == "2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1"


@pytest.mark.parametrize(("candidate_range", "row"), (("A3:AQ605", 6), ("A3:AQ607", 6), ("A3:AQ606", 3), ("A3:AQ606", 606)))
def test_unchanged_overexpanded_or_out_of_range_candidates_fail_typed(tmp_path: Path, candidate_range: str, row: int) -> None:
    control = _book(tmp_path / "control.xlsx", FILTER)
    candidate = _book(
        tmp_path / "candidate.xlsx",
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!{candidate_range}</definedName>',
    )
    with pytest.raises(OPCWorkbookFilterDatabaseInsertionOracleError) as captured:
        validate_filter_database_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=row)
    assert len(captured.value.as_tuple()) == 4


@pytest.mark.parametrize("candidate_names", (
    '<definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A3:AR606</definedName>',
    '<definedName name="_xlnm._FilterDatabase" localSheetId="1">Лист &apos;Два&apos;!A3:AQ606</definedName>',
))
def test_changed_columns_or_worksheet_owner_fail_typed(tmp_path: Path, candidate_names: str) -> None:
    control = _book(tmp_path / "control.xlsx", FILTER)
    candidate = _book(tmp_path / "candidate.xlsx", candidate_names)
    with pytest.raises(OPCWorkbookFilterDatabaseInsertionOracleError) as captured:
        validate_filter_database_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=6)
    assert len(captured.value.as_tuple()) == 4


@pytest.mark.parametrize("candidate_opaque", (
    '<definedName name="Opaque" localSheetId="1" hidden="true">unchanged</definedName>' + FILTER.replace("$a$3:$aq$605", "A3:AQ606"),
    '<definedName name="Opaque" hidden="true">unchanged</definedName><definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A3:AQ606</definedName>',
    '<definedName name="Opaque" localSheetId="1" hidden="false">unchanged</definedName><definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A3:AQ606</definedName>',
    '<definedName name="Opaque" localSheetId="1" hidden="true">changed</definedName><definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A3:AQ606</definedName>',
))
def test_changed_unrelated_name_order_scope_hidden_or_expression_fails_typed(tmp_path: Path, candidate_opaque: str) -> None:
    control = _book(
        tmp_path / "control.xlsx",
        FILTER + '<definedName name="Opaque" localSheetId="1" hidden="true">unchanged</definedName>',
    )
    candidate = _book(tmp_path / "candidate.xlsx", candidate_opaque)
    with pytest.raises(OPCWorkbookFilterDatabaseInsertionOracleError) as captured:
        validate_filter_database_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=6)
    assert len(captured.value.as_tuple()) == 4


def test_missing_or_duplicate_target_owner_has_exact_four_field_tuple(tmp_path: Path) -> None:
    control = _book(tmp_path / "control.xlsx", FILTER)
    missing = _book(tmp_path / "missing.xlsx", '<definedName name="opaque">value</definedName>')
    with pytest.raises(OPCWorkbookFilterDatabaseInsertionOracleError) as captured:
        validate_filter_database_middle_insert(control, missing, sheet_name=SHEET, insertion_row=6)
    assert captured.value.as_tuple() == ("missing-filter-database-owner", SHEET, "owner_count", "0")

    duplicate = _book(tmp_path / "duplicate.xlsx", FILTER + FILTER.replace("605", "606"))
    with pytest.raises(OPCWorkbookFilterDatabaseInsertionOracleError) as captured:
        validate_filter_database_middle_insert(control, duplicate, sheet_name=SHEET, insertion_row=6)
    assert captured.value.as_tuple() == ("ambiguous-filter-database-owner", SHEET, "owner_count", "multiple")
