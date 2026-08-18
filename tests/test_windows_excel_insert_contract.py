from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "windows_excel_insert.ps1"
MODULE = ROOT / "scripts" / "WindowsExcelInsert.Contract.psm1"
PESTER = ROOT / "tests" / "windows_excel_insert_contract.Tests.ps1"


def test_contract_has_atomic_bom_free_structured_protocol_and_error_envelope() -> None:
    text = MODULE.read_text(encoding="utf-8")
    assert "function Write-AtomicContractJson" in text
    assert "UTF8Encoding]::new($false)" in text
    assert "$stream.Flush($true)" in text
    assert "contract_version = 'powershell-row-contract-v3'" in text
    for field in ("stage", "hresult", "winerror", "primary", "cleanup"):
        assert field in text
    assert json.loads('{"kind":"progress","stage":"ack","primary":null,"cleanup":null}')["stage"] == "ack"


def test_lease_ack_precedes_every_workbook_open_and_uses_exact_nonce() -> None:
    text = MODULE.read_text(encoding="utf-8")
    assert text.index("Write-AtomicContractJson -Path ([string]$Data.lease_file)") < text.index("Wait-ExactLeaseAck $Data") < text.index("$excel.Workbooks.Open")
    assert "$ack.operation_id -eq $Data.operation_id" in text
    assert "$ack.owner_nonce -eq $Data.owner_nonce" in text
    assert "$ack.pair_nonce -eq $Data.pair_nonce" in text
    assert "adapter_pid" in text and "excel_pid" in text and "excel_hwnd" in text


def test_contract_validates_row_group_allowlists_and_performs_one_exact_insert() -> None:
    text = MODULE.read_text(encoding="utf-8")
    assert "function Test-RowContractRequest" in text
    for name in ("group_start_row", "expected_next_header_row", "source_row", "template_row", "ordinal_map"):
        assert name in text
    assert "$column -gt 24" in text and "$column -ne 27" in text
    assert text.count(".Insert(-4121, 0)") == 1
    assert ".FormulaR1C1 = [string]$Data.formula_y_r1c1" in text
    assert ".FormulaR1C1 = [string]$Data.formula_z_r1c1" in text
    assert "$sheet.Hyperlinks.Add($target" in text
    assert "foreach ($entry in @($Data.ordinal_map))" in text


def test_owned_cleanup_and_pester_fault_matrix_are_explicit() -> None:
    text = MODULE.read_text(encoding="utf-8")
    assert "if ($excel -and $ownedExcel) { $excel.Quit() }" in text
    assert "Release-ComProxy" in text
    pester = PESTER.read_text(encoding="utf-8")
    for marker in ("6", "10", "104", "open", "insert", "calc", "save", "cleanup"):
        assert marker in pester
    assert "windows_powershell_contract_unavailable" in pester
    assert "Invoke-ExcelRowContract" in SCRIPT.read_text(encoding="utf-8")
