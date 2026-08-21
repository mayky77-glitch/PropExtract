"""Bounded read-only contract for the X14 middle-row insertion oracle."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

import rns_import_server.opc_worksheet_x14_cf_insertion_oracle as oracle
from rns_import_server.opc_worksheet_x14_cf_insertion_oracle import (
    OPCWorksheetX14CfInsertionOracleError,
    validate_x14_cf_middle_insert,
)
from rns_import_server.opc_worksheet_x14_cf_owner_topology import read_worksheet_x14_cf_sqref_envelope
from tests.opc_worksheet_x14_cf_sqref_fixture_factory import corpus, extension, owner, rule


SHEET = "Первый"
GUIDS = (
    "{00112233-4455-6677-8899-AABBCCDDEEF1}",
    "{00112233-4455-6677-8899-AABBCCDDEEF2}",
    "{00112233-4455-6677-8899-AABBCCDDEEF3}",
)


def _package(path: Path, *, rows: tuple[int, ...] = (6,), dxf: str = "<x14:dxf/>", candidate_dxf: str | None = None,
             candidate_ids: tuple[str, ...] | None = None, candidate_priorities: tuple[str, ...] | None = None,
             candidate_types: tuple[str, ...] | None = None, reverse: bool = False) -> tuple[Path, Path]:
    controls = []
    candidates = []
    for index, row in enumerate(rows):
        rule_id = GUIDS[index]
        source = rule(priority=str(index + 1), rule_id=rule_id, formula=f"A{row}&gt;0", children=f"<xm:f>A{row}&gt;0</xm:f>{dxf}")
        controls.append(owner(source, sqref=f"<xm:sqref>A{row} B{row - 1}:I{row - 1}</xm:sqref>"))
        shifted = rule(priority=(candidate_priorities or tuple(str(i + 1) for i in range(len(rows))))[index],
                       rule_id=(candidate_ids or GUIDS)[index], formula=f"A{row + 1}&gt;0",
                       children=f"<xm:f>A{row + 1}&gt;0</xm:f>{candidate_dxf or dxf}")
        if candidate_types:
            shifted = shifted.replace('type="expression"', f'type="{candidate_types[index]}"')
        candidates.append(owner(shifted, sqref=f"<xm:sqref>A{row + 1} B{row - 1}:I{row}</xm:sqref>"))
    control = corpus(path.with_name(f"{path.stem}-control.xlsx"), first=extension("".join(controls)))
    if reverse:
        candidates.reverse()
    candidate = corpus(path.with_name(f"{path.stem}-candidate.xlsx"), first=extension("".join(candidates)))
    return control, candidate


@pytest.mark.parametrize(("row", "source_coverage"), ((6, 8), (10, 8), (104, 8)))
def test_expected_geometry_and_formula_shift_for_insert_rows(tmp_path: Path, row: int, source_coverage: int) -> None:
    control, candidate = _package(tmp_path / f"row-{row}.xlsx", rows=(row,))
    validate_x14_cf_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=row, format_source_row=row - 1)
    projection = read_worksheet_x14_cf_sqref_envelope(candidate)
    ranges = projection.worksheets[0].containers[0].ranges
    assert sum(item.min_row <= row <= item.max_row for item in ranges) == source_coverage // 8


@pytest.mark.parametrize("kind", ("guid", "order", "type", "priority"))
def test_guid_order_type_and_priority_mismatches_block(tmp_path: Path, kind: str) -> None:
    options = {
        "guid": {"candidate_ids": ("{00112233-4455-6677-8899-AABBCCDDEEA0}", GUIDS[1])},
        "order": {"reverse": True},
        "type": {"candidate_types": ("cellIs", "expression")},
        "priority": {"candidate_priorities": ("99", "2")},
    }
    control, candidate = _package(tmp_path / f"{kind}.xlsx", rows=(6, 10), **options[kind])
    with pytest.raises(OPCWorksheetX14CfInsertionOracleError) as captured:
        validate_x14_cf_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=6, format_source_row=5)
    assert len(captured.value.as_tuple()) == 4


def test_semantic_dxf_detects_change_but_ignores_prefix_and_attribute_order(tmp_path: Path) -> None:
    original = '<x14:dxf><x14:font a="1" z="2"/></x14:dxf>'
    equivalent = '<z:dxf xmlns:z="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"><z:font z="2" a="1"/></z:dxf>'
    control, candidate = _package(tmp_path / "dxf.xlsx", dxf=original, candidate_dxf=equivalent)
    validate_x14_cf_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=6, format_source_row=5)
    _, candidate = _package(tmp_path / "dxf-changed.xlsx", dxf=original, candidate_dxf=equivalent.replace('z="2"', 'z="3"'))
    with pytest.raises(OPCWorksheetX14CfInsertionOracleError, match="x14-cf-dxf-mismatch"):
        validate_x14_cf_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=6, format_source_row=5)
    control, candidate = _package(tmp_path / "dxf-child-tail.xlsx", dxf=original,
                                  candidate_dxf=original.replace("/></x14:dxf>", "></x14:font>changed</x14:dxf>"))
    with pytest.raises(OPCWorksheetX14CfInsertionOracleError, match="x14-cf-dxf-mismatch"):
        validate_x14_cf_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=6, format_source_row=5)


def test_unsupported_formula_and_malformed_candidate_block_without_writes(monkeypatch, tmp_path: Path) -> None:
    control, candidate = _package(tmp_path / "negative.xlsx")
    control_hash = sha256(control.read_bytes()).hexdigest()
    monkeypatch.setattr(oracle, "Translator", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("unsupported")))
    with pytest.raises(OPCWorksheetX14CfInsertionOracleError, match="unsupported-x14-cf-formula"):
        validate_x14_cf_middle_insert(control, candidate, sheet_name=SHEET, insertion_row=6, format_source_row=5)
    monkeypatch.undo()
    malformed = corpus(
        tmp_path / "malformed.xlsx",
        first=extension(owner(rule(formula="A7&gt;0"), sqref="<xm:sqref>A7 B0:I6</xm:sqref>")),
    )
    malformed_hash = sha256(malformed.read_bytes()).hexdigest()
    with pytest.raises(OPCWorksheetX14CfInsertionOracleError, match="invalid-x14-cf-insertion-input"):
        validate_x14_cf_middle_insert(control, malformed, sheet_name=SHEET, insertion_row=6, format_source_row=5)
    assert sha256(control.read_bytes()).hexdigest() == control_hash
    assert sha256(malformed.read_bytes()).hexdigest() == malformed_hash


def test_real_source_projection_and_fingerprints_are_read_only() -> None:
    source = Path(__file__).resolve().parents[4] / "Автоматизация РнС и ГРО" / "Реестр РНС Иркутск.xlsx"
    before = sha256(source.read_bytes()).hexdigest()
    projection = read_worksheet_x14_cf_sqref_envelope(source)
    rules = tuple(rule for sheet in projection.worksheets for container in sheet.containers for rule in container.rules)
    ranges = tuple(item for sheet in projection.worksheets for container in sheet.containers for item in container.ranges)
    fingerprints = oracle._dxf_fingerprints(str(source))
    assert len(rules) == len(fingerprints) == 1558
    assert len(ranges) == 2473
    assert len({rule.formula for rule in rules}) == 94
    assert len(set(fingerprints.values())) == 7
    assert tuple(sum(item.min_row <= row <= item.max_row for item in ranges) for row in (6, 10, 104)) == (8, 8, 13)
    containers = tuple(container for sheet in projection.worksheets for container in sheet.containers)
    assert tuple(sum(any(item.min_row <= row - 1 <= item.max_row for item in container.ranges) for container in containers)
                 for row in (6, 10, 104)) == (8, 30, 18)
    assert sha256(source.read_bytes()).hexdigest() == before == "2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1"
