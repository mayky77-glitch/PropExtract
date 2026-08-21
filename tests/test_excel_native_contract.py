from pathlib import Path
import os

import pytest

from rns_import_server.excel_native import NativeExcelError, NativeInsertRequest, native_excel_available, run_native_insert


def test_hosted_non_windows_is_a_typed_safe_negative_path(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 6, tmp_path / "lease.json", tmp_path / "ack.json", "Реестр РНС", {}, None, "middle_insert")
    if not native_excel_available():
        with pytest.raises(NativeExcelError, match="excel_required_for_middle_insert"):
            run_native_insert(request, script=tmp_path / "helper.ps1")


def test_native_request_carries_pair_and_lease_paths(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 10, tmp_path / "lease.json", tmp_path / "ack.json", "Реестр РНС", {}, None, "blank_fill")
    assert request.payload()["pair_nonce"] == "pair"
    assert request.payload()["insertion_row"] == 10
    assert request.payload()["mutation_mode"] == "blank_fill"


def test_invalid_native_mutation_mode_fails_before_request_file_or_helper_launch(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 10, tmp_path / "ops" / "lease.json", tmp_path / "ops" / "ack.json", "Реестр РНС", {}, None, "wrong")
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(request, script=tmp_path / "helper.ps1")
    assert (captured.value.code, captured.value.stage) == ("native_mutation_mode_invalid", "pre_open")
    assert not (tmp_path / "ops").exists()


@pytest.mark.parametrize("mode", ["MIDDLE_INSERT", "Middle_Insert", None])
def test_powershell_rejects_noncanonical_mode_before_com_and_has_one_middle_insert(mode: str | None) -> None:
    script = (Path(__file__).parents[1] / "scripts" / "windows_excel_insert.ps1").read_text(encoding="utf-8")
    guard = "if ($data.mutation_mode -cnotin @('middle_insert', 'blank_fill'))"
    assert guard in script and mode not in {"middle_insert", "blank_fill"}
    assert script.index(guard) < script.index("New-Object -ComObject Excel.Application")
    assert "if ($data.mutation_mode -ceq 'middle_insert')" in script
    assert script.count(".Insert(-4121, 0)") == 1
