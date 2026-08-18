from pathlib import Path
import os

import pytest

from rns_import_server.excel_native import NativeExcelError, NativeInsertRequest, native_excel_available, run_native_insert, validate_lease, validate_request


def _request(tmp_path: Path, row: int = 6, **kwargs) -> NativeInsertRequest:
    fields = kwargs.pop("fields", {})
    hyperlink = kwargs.pop("hyperlink", None)
    return NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", row, tmp_path / "lease.json", tmp_path / "ack.json", "Реестр РНС", fields, hyperlink, **kwargs)


def test_hosted_non_windows_is_a_typed_safe_negative_path(tmp_path: Path) -> None:
    request = _request(tmp_path, template_formula_r1c1={25: "=RC[-1]", 26: "=RC[-1]"})
    if not native_excel_available():
        with pytest.raises(NativeExcelError, match="excel_required_for_middle_insert"):
            run_native_insert(request, script=tmp_path / "helper.ps1", lease_recorder=lambda lease: None, process_probe=lambda pid: {})


def test_native_request_carries_pair_and_lease_paths(tmp_path: Path) -> None:
    request = _request(tmp_path, 10, template_formula_r1c1={25: "=RC[-1]", 26: "=RC[-1]"})
    assert request.payload()["pair_nonce"] == "pair"
    assert request.payload()["insertion_row"] == 10


@pytest.mark.parametrize("row", [6, 10, 104])
def test_explicit_sheet_contract_accepts_only_safe_insert_rows(tmp_path: Path, row: int) -> None:
    validate_request(_request(tmp_path, row, template_formula_r1c1={25: "=RC[-1]", 26: "=RC[-1]"}))


def test_request_rejects_wrong_sheet_allowlist_formula_and_hyperlink(tmp_path: Path) -> None:
    with pytest.raises(NativeExcelError, match="native_insert_request_invalid"):
        validate_request(NativeInsertRequest("op", "owner", "pair", tmp_path / "c", tmp_path / "d", 6, tmp_path / "l", tmp_path / "a", "", {}, None))
    with pytest.raises(NativeExcelError, match="native_field_not_allowlisted"):
        validate_request(_request(tmp_path, fields={26: "bad"}))
    with pytest.raises(NativeExcelError, match="native_hyperlink_invalid"):
        validate_request(_request(tmp_path, hyperlink="javascript:bad"))
    with pytest.raises(NativeExcelError, match="native_template_formula_invalid"):
        validate_request(_request(tmp_path, template_formula_r1c1={25: "bad"}))


def test_truthful_lease_rejects_pid_reuse_image_and_hwnd_mismatch(tmp_path: Path) -> None:
    request = _request(tmp_path)
    lease = {"excel_adapter": "com", "adapter_pid": 11, "adapter_started_at": "a", "excel_pid": 22, "excel_hwnd": 33, "excel_process_started_at": "s", "excel_image": "EXCEL.EXE", "excel_build": "b"}
    validate_lease(lease, request, process_probe=lambda pid: {"image": "EXCEL.EXE", "started_at": "s", "hwnd": 33})
    with pytest.raises(NativeExcelError, match="excel_lease_process_mismatch"):
        validate_lease(lease, request, process_probe=lambda pid: {"image": "EXCEL.EXE", "started_at": "other", "hwnd": 33})
    with pytest.raises(NativeExcelError, match="excel_lease_process_mismatch"):
        validate_lease(lease, request, process_probe=lambda pid: {"image": "OTHER.EXE", "started_at": "s", "hwnd": 33})
