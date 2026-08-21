"""Acceptance contract for the worksheet-structure middle-insert oracle."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

import pytest

from rns_import_server.opc_worksheet_structure_insertion_oracle import (
    OPCWorksheetStructureInsertionOracleError,
    validate_worksheet_structure_middle_insert,
)
from rns_import_server.opc_worksheet_structure_reader import read_worksheet_structure_semantics
import rns_import_server.opc_worksheet_structure_insertion_oracle as oracle


SHEET = "Реестр РНС"
SOURCE = Path(__file__).resolve().parents[4] / "Автоматизация РнС и ГРО" / "Реестр РНС Иркутск.xlsx"
SML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _cell(row: int, column: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _mapped_reference(reference: str, insertion_row: int) -> str:
    first, *tail = reference.split(":")
    points = (first, tail[0] if tail else first)

    def parse(value: str) -> tuple[int, int]:
        letters = "".join(char for char in value if char.isalpha())
        row = int("".join(char for char in value if char.isdigit()))
        column = 0
        for char in letters.upper():
            column = column * 26 + ord(char) - ord("A") + 1
        return row, column

    mapped = []
    for row, column in map(parse, points):
        mapped.append(_cell(row + (row >= insertion_row), column))
    if points[0] != points[1] and parse(points[0])[0] < insertion_row <= parse(points[1])[0]:
        row, column = parse(points[1]); mapped[-1] = _cell(row + 1, column)
    return mapped[0] if mapped[0] == mapped[1] else ":".join(mapped)


def _candidate_for(source: Path, destination: Path, insertion_row: int) -> Path:
    target_part = next(
        item.worksheet.worksheet_part.value
        for item in read_worksheet_structure_semantics(source).worksheets
        if item.worksheet.name == SHEET
    )
    with ZipFile(source) as before, ZipFile(destination, "w", ZIP_DEFLATED) as after:
        for info in before.infolist():
            payload = before.read(info)
            if info.filename == target_part:
                root = ET.fromstring(payload)
                for tag, attribute in (("dimension", "ref"), ("autoFilter", "ref"), ("mergeCell", "ref")):
                    for element in root.findall(f".//{{{SML}}}{tag}"):
                        element.set(attribute, _mapped_reference(element.attrib[attribute], insertion_row))
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            after.writestr(info, payload)
    return destination


@pytest.mark.parametrize("row", (6, 10, 104))
def test_real_source_mapping_and_hash_are_read_only(tmp_path: Path, row: int) -> None:
    before = sha256(SOURCE.read_bytes()).hexdigest()
    candidate = _candidate_for(SOURCE, tmp_path / f"candidate-{row}.xlsx", row)
    evidence = validate_worksheet_structure_middle_insert(SOURCE, candidate, sheet_name=SHEET, insertion_row=row)
    assert (evidence.control_dimension.start, evidence.control_dimension.end, evidence.candidate_dimension.end) == (
        "A1", "AQ1001", "AQ1002",
    )
    control = next(item for item in read_worksheet_structure_semantics(SOURCE).worksheets if item.worksheet.name == SHEET)
    assert (control.auto_filter.reference.start, control.auto_filter.reference.end, len(control.merges)) == ("A3", "AQ605", 12)
    candidate_structure = next(item for item in read_worksheet_structure_semantics(candidate).worksheets if item.worksheet.name == SHEET)
    changed = sum(before != after for before, after in zip(control.merges, candidate_structure.merges))
    assert changed == (5 if row == 6 else 0)
    assert sha256(SOURCE.read_bytes()).hexdigest() == before == "2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1"


def test_mismatch_dependency_failure_and_invalid_bounds_are_typed(tmp_path: Path) -> None:
    candidate = _candidate_for(SOURCE, tmp_path / "candidate.xlsx", 6)
    with ZipFile(candidate) as archive:
        members = {info.filename: archive.read(info) for info in archive.infolist()}
    part = next(item.worksheet.worksheet_part.value for item in read_worksheet_structure_semantics(SOURCE).worksheets if item.worksheet.name == SHEET)
    root = ET.fromstring(members[part]); root.find(f".//{{{SML}}}dimension").set("ref", "A1:AQ1001")
    members[part] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    broken = tmp_path / "broken.xlsx"
    with ZipFile(broken, "w", ZIP_DEFLATED) as archive:
        for name, payload in members.items(): archive.writestr(name, payload)
    with pytest.raises(OPCWorksheetStructureInsertionOracleError) as captured:
        validate_worksheet_structure_middle_insert(SOURCE, broken, sheet_name=SHEET, insertion_row=6)
    assert captured.value.as_tuple() == ("worksheet-structure-range-mismatch", SHEET, "dimension", "geometry")
    with pytest.raises(OPCWorksheetStructureInsertionOracleError) as captured:
        validate_worksheet_structure_middle_insert(SOURCE, tmp_path / "missing.xlsx", sheet_name=SHEET, insertion_row=6)
    assert captured.value.as_tuple()[0:3] == ("invalid-worksheet-structure-insertion-input", SHEET, "candidate")
    with pytest.raises(OPCWorksheetStructureInsertionOracleError) as captured:
        validate_worksheet_structure_middle_insert(SOURCE, candidate, sheet_name=SHEET, insertion_row=True)
    assert captured.value.code == "invalid-worksheet-structure-insertion-row"


class _PathLike:
    def __init__(self, value: Path) -> None:
        self.value, self.calls = value, 0

    def __fspath__(self) -> str:
        self.calls += 1
        return str(self.value)


def test_pathlike_is_accepted_and_source_is_not_saved(tmp_path: Path) -> None:
    candidate = _candidate_for(SOURCE, tmp_path / "candidate.xlsx", 10)
    before = sha256(SOURCE.read_bytes()).hexdigest()
    control_path, candidate_path = _PathLike(SOURCE), _PathLike(candidate)
    evidence = validate_worksheet_structure_middle_insert(control_path, candidate_path, sheet_name=SHEET, insertion_row=10)
    assert evidence.worksheet.name == SHEET
    assert (control_path.calls, candidate_path.calls) == (1, 1)
    assert sha256(SOURCE.read_bytes()).hexdigest() == before


def _range(first: int, last: int) -> object:
    return oracle.A1Range(f"A{first}", f"C{last}", first, last, 1, 3)


def _structure(*, dimension: object = _range(1, 10), auto: object = _range(3, 10), merges: tuple[object, ...] = (_range(2, 2), _range(6, 6)), identity: object | None = None, other_identity: object | None = None, unrelated: str = "same") -> object:
    target = identity or SimpleNamespace(name="Target")
    other = other_identity or SimpleNamespace(name="Other")
    return SimpleNamespace(worksheets=(
        SimpleNamespace(worksheet=target, dimension=dimension, auto_filter=SimpleNamespace(reference=auto) if auto else None, merges=merges, rows="target"),
        SimpleNamespace(worksheet=other, dimension=_range(1, 2), auto_filter=None, merges=(), rows=unrelated),
    ))


@pytest.mark.parametrize(("case", "row", "expected"), (
    ("first-error", 6, ("worksheet-structure-range-mismatch", "Target", "dimension", "geometry")),
    ("bounds-zero", 0, ("invalid-worksheet-structure-insertion-row", "Target", "insertion_row", "0")),
    ("bounds-bool", True, ("invalid-worksheet-structure-insertion-row", "Target", "insertion_row", "True")),
    ("bounds-max-plus-one", 1_048_577, ("invalid-worksheet-structure-insertion-row", "Target", "insertion_row", "1048577")),
    ("auto-filter", 6, ("worksheet-structure-presence-mismatch", "Target", "autoFilter", "missing-or-extra")),
    ("merge-order", 6, ("worksheet-structure-range-mismatch", "Target", "mergeCells", "0")),
    ("merge-count", 6, ("worksheet-structure-count-mismatch", "Target", "mergeCells", "count")),
    ("identity-order", 6, ("worksheet-identity-order-mismatch", "Target", "worksheets", "identity-or-order")),
    ("unrelated", 6, ("unrelated-worksheet-structure-mismatch", "Other", "structure", "changed")),
))
def test_first_error_and_structure_boundary_matrix(monkeypatch: pytest.MonkeyPatch, case: str, row: int, expected: tuple[str, str, str, str]) -> None:
    target = SimpleNamespace(name="Target")
    other = SimpleNamespace(name="Other")
    control = _structure(identity=target, other_identity=other)
    candidate = _structure(dimension=_range(1, 11), auto=_range(3, 11), merges=(_range(2, 2), _range(7, 7)), identity=target, other_identity=other)
    if case == "first-error": candidate = _structure(dimension=_range(1, 10), auto=_range(3, 11), merges=(), identity=target, other_identity=other)
    if case == "auto-filter": candidate = _structure(dimension=_range(1, 11), auto=None, merges=(_range(2, 2), _range(7, 7)), identity=target, other_identity=other)
    if case == "merge-order": candidate = _structure(dimension=_range(1, 11), auto=_range(3, 11), merges=(_range(7, 7), _range(2, 2)), identity=target, other_identity=other)
    if case == "merge-count": candidate = _structure(dimension=_range(1, 11), auto=_range(3, 11), merges=(_range(2, 2),), identity=target, other_identity=other)
    if case == "identity-order": candidate = _structure(dimension=_range(1, 11), auto=_range(3, 11), merges=(_range(2, 2), _range(7, 7)), identity=SimpleNamespace(name="Target", changed=True), other_identity=other)
    if case == "unrelated": candidate = _structure(dimension=_range(1, 11), auto=_range(3, 11), merges=(_range(2, 2), _range(7, 7)), identity=target, other_identity=other, unrelated="changed")
    records = iter((control, candidate))
    monkeypatch.setattr(oracle, "read_worksheet_structure_semantics", lambda _path: next(records))
    with pytest.raises(OPCWorksheetStructureInsertionOracleError) as captured:
        oracle.validate_worksheet_structure_middle_insert("control", "candidate", sheet_name="Target", insertion_row=row)
    assert captured.value.as_tuple() == expected


@pytest.mark.parametrize("row", (1, 1_048_576))
def test_dimension_start_and_maximum_row_are_valid_or_fail_before_mapping(monkeypatch: pytest.MonkeyPatch, row: int) -> None:
    target = SimpleNamespace(name="Target")
    other = SimpleNamespace(name="Other")
    if row == 1:
        control = _structure(dimension=_range(1, 10), auto=None, merges=(), identity=target, other_identity=other)
        candidate = _structure(dimension=_range(2, 11), auto=None, merges=(), identity=target, other_identity=other)
        records = iter((control, candidate))
        monkeypatch.setattr(oracle, "read_worksheet_structure_semantics", lambda _path: next(records))
        assert oracle.validate_worksheet_structure_middle_insert("control", "candidate", sheet_name="Target", insertion_row=row).insertion_row == 1
        return
    control = _structure(dimension=_range(1, 1_048_576), auto=None, merges=(), identity=target, other_identity=other)
    records = iter((control, control))
    monkeypatch.setattr(oracle, "read_worksheet_structure_semantics", lambda _path: next(records))
    with pytest.raises(OPCWorksheetStructureInsertionOracleError) as captured:
        oracle.validate_worksheet_structure_middle_insert("control", "candidate", sheet_name="Target", insertion_row=row)
    assert captured.value.as_tuple() == ("invalid-worksheet-structure-insertion-row", "Target", "insertion_row", "1048576")
