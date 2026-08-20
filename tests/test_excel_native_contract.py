from pathlib import Path
import os

import pytest

from rns_import_server.excel_native import NativeExcelError, NativeInsertRequest, native_excel_available, run_native_insert


def test_hosted_non_windows_is_a_typed_safe_negative_path(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 6, tmp_path / "lease.json", tmp_path / "ack.json", "Реестр РНС", {}, None)
    if not native_excel_available():
        with pytest.raises(NativeExcelError, match="excel_required_for_middle_insert"):
            run_native_insert(request, script=tmp_path / "helper.ps1")


def test_native_request_carries_pair_and_lease_paths(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 10, tmp_path / "lease.json", tmp_path / "ack.json", "Реестр РНС", {}, None)
    assert request.payload()["pair_nonce"] == "pair"
    assert request.payload()["insertion_row"] == 10
