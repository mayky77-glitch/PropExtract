from __future__ import annotations
from dataclasses import FrozenInstanceError
import pytest
from rns_import_server.opc_worksheet_structure_reader import OPCWorksheetStructureReaderError, read_worksheet_structure_semantics
from tests.opc_worksheet_structure_fixture_factory import package, worksheet

def error(path):
    with pytest.raises(OPCWorksheetStructureReaderError) as captured: read_worksheet_structure_semantics(path)
    return captured.value.as_tuple()

def test_reads_immutable_native_geometry_and_row_properties(tmp_path):
    rows = '<row r="6" ht="12.5" s="3" customHeight="1" customFormat="0" hidden="true" outlineLevel="7" collapsed="false"><c r="A6"><v>1</v></c></row><row r="10"><c r="B10"><v>2</v></c></row><row r="104"><c r="C104"><v>3</v></c></row>'
    result = read_worksheet_structure_semantics(package(tmp_path / "ok.xlsx", sheet_one=worksheet(rows=rows)))
    first = result.worksheets[0]
    assert [(row.row, row.height, row.style_index, row.hidden, row.outline_level) for row in first.rows] == [(6, 12.5, 3, True, 7), (10, None, None, None, None), (104, None, None, None, None)]
    assert [(item.start, item.end) for item in first.merges] == [("A6", "B6"), ("A10", "C104")]
    assert first.dimension and first.dimension.max_row == 104 and first.auto_filter and first.auto_filter.reference.start == "A6"
    with pytest.raises(FrozenInstanceError): first.rows[0].row = 7

@pytest.mark.parametrize(("sheet", "expected"), [
    (worksheet(dimension='<dimension ref="A:A"/>'), ("invalid-a1-range", "xl/worksheets/first.xml", "ref", "A:A")),
    (worksheet(merges='<mergeCells count="2"><mergeCell ref="A6:B6"/></mergeCells>'), ("merge-count-mismatch", "xl/worksheets/first.xml", "count", "2")),
    (worksheet(rows='<row r="10"><c r="B10"><v>1</v></c></row><row r="6"><c r="A6"><v>1</v></c></row>'), ("out-of-order-row", "xl/worksheets/first.xml", "r", "6")),
    (worksheet(rows='<row r="6" hidden="yes"><c r="A6"><v>1</v></c></row>'), ("invalid-row-property", "xl/worksheets/first.xml", "hidden", "yes")),
    (worksheet(rows='<row r="6" outlineLevel="8"><c r="A6"><v>1</v></c></row>'), ("invalid-row-property", "xl/worksheets/first.xml", "outlineLevel", "8")),
    (worksheet(merges='<mergeCells count="2"><mergeCell ref="A6:B6"/><mergeCell ref="A6:B6"/></mergeCells>'), ("duplicate-merge-range", "xl/worksheets/first.xml", "ref", "A6:B6")),
    (worksheet(auto_filter='<autoFilter ref="C104:A6"/>'), ("invalid-a1-range", "xl/worksheets/first.xml", "ref", "C104:A6")),
])
def test_typed_structure_defects(tmp_path, sheet, expected):
    assert error(package(tmp_path / "bad.xlsx", sheet_one=sheet)) == expected

def test_boundaries_optional_containers_and_order(tmp_path):
    good = worksheet(dimension='<dimension ref="$A$1:$XFD$1048576"/>', rows='<row r="1"><c r="A1"><v>1</v></c></row><row r="1048576"><c r="XFD1048576"><v>2</v></c></row>', auto_filter='', merges='')
    record = read_worksheet_structure_semantics(package(tmp_path / "limits.xlsx", sheet_one=good)).worksheets[0]
    assert record.dimension and (record.dimension.start, record.dimension.end) == ("A1", "XFD1048576")
    bad_order = f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData><mergeCells count="0"/><autoFilter ref="A6"/></worksheet>'.encode()
    assert error(package(tmp_path / "order.xlsx", sheet_one=bad_order)) == ("invalid-worksheet-child-order", "xl/worksheets/first.xml", "tag", "['{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData', '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}mergeCells', '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}autoFilter']")


@pytest.mark.parametrize("reference", ["", "A0", "XFE1", "A6:B5", "B6:A7", "Sheet1!A6", "A:A", "6:6", "A6:B6:C6"])
def test_rejects_all_non_rectangular_or_out_of_grid_a1_forms(tmp_path, reference):
    assert error(package(tmp_path / "a1.xlsx", sheet_one=worksheet(dimension=f'<dimension ref="{reference}"/>'))) == ("invalid-a1-range", "xl/worksheets/first.xml", "ref", reference)


def test_rejects_owned_unknown_duplicate_mixed_and_nested_content(tmp_path):
    unknown = worksheet(dimension='<dimension ref="A6" unexpected="x"/>')
    assert error(package(tmp_path / "unknown.xlsx", sheet_one=unknown)) == ("unknown-dimension-attribute", "xl/worksheets/first.xml", "attribute", "unexpected")
    duplicate = f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A6"/><dimension ref="A6"/><sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData></worksheet>'.encode()
    assert error(package(tmp_path / "duplicate.xlsx", sheet_one=duplicate)) == ("duplicate-worksheet-container", "xl/worksheets/first.xml", "dimension", "")
    nested = worksheet(auto_filter='<autoFilter ref="A6"><filterColumn/></autoFilter>')
    assert error(package(tmp_path / "nested.xlsx", sheet_one=nested)) == ("invalid-auto-filter-content", "xl/worksheets/first.xml", "autoFilter", "nested")


@pytest.mark.parametrize(("height", "style", "outline", "expected"), [
    ("+12.5", "+0003", "-0", (12.5, 3, 0)),
    (".5", "0000000000000000000000000000000000000000000000000000000000000000", " 0 ", (0.5, 0, 0)),
    ("12.", "0", "0", (12.0, 0, 0)),
    ("1e2", "0", "0", (100.0, 0, 0)),
])
def test_row_properties_match_accepted_compatibility_lexicals(tmp_path, height, style, outline, expected):
    rows = f'<row r="6" ht="{height}" s="{style}" outlineLevel="{outline}" customHeight="0" customFormat="false" hidden="0" collapsed="false"><c r="A6"><v>1</v></c></row>'
    item = read_worksheet_structure_semantics(package(tmp_path / "row.xlsx", sheet_one=worksheet(rows=rows))).worksheets[0].rows[0]
    assert (item.height, item.style_index, item.outline_level, item.custom_height, item.hidden) == (*expected, False, False)


def test_merge_count_order_and_normalized_alias_are_strict(tmp_path):
    missing = worksheet(merges='<mergeCells><mergeCell ref="A6:B6"/></mergeCells>')
    assert error(package(tmp_path / "missing-count.xlsx", sheet_one=missing)) == ("missing-merge-count", "xl/worksheets/first.xml", "count", "")
    reversed_order = worksheet(merges='<mergeCells count="2"><mergeCell ref="A10:B10"/><mergeCell ref="A6:B6"/></mergeCells>')
    assert error(package(tmp_path / "merge-order.xlsx", sheet_one=reversed_order)) == ("out-of-order-merge-range", "xl/worksheets/first.xml", "ref", "A6:B6")
    alias = worksheet(merges='<mergeCells count="2"><mergeCell ref="$a$6:$B$6"/><mergeCell ref="A6:B6"/></mergeCells>')
    assert error(package(tmp_path / "merge-alias.xlsx", sheet_one=alias)) == ("duplicate-merge-range", "xl/worksheets/first.xml", "ref", "A6:B6")


def test_rejects_bare_root_attributes_and_owned_namespace_collisions(tmp_path):
    root_attribute = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" bogus="x"><sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData></worksheet>'
    assert error(package(tmp_path / "root-attr.xlsx", sheet_one=root_attribute)) == ("unknown-worksheet-attribute", "xl/worksheets/first.xml", "attribute", "bogus")
    collision = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:x="urn:collision"><x:dimension ref="A6"/><sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData></worksheet>'
    assert error(package(tmp_path / "collision.xlsx", sheet_one=collision)) == ("invalid-owned-namespace", "xl/worksheets/first.xml", "tag", "{urn:collision}dimension")


def test_reports_preflight_evidence_without_claiming_safety(tmp_path):
    sheet = worksheet(merges='<mergeCells count="1"><mergeCell ref="A6:C104"/></mergeCells>')
    record = read_worksheet_structure_semantics(package(tmp_path / "preflight.xlsx", sheet_one=sheet)).worksheets[0]
    assert any(item.min_row < 10 <= item.max_row for item in record.merges)
    assert record.dimension and record.dimension.min_row <= 10 <= record.dimension.max_row
    assert record.auto_filter and record.auto_filter.reference.min_row <= 10 <= record.auto_filter.reference.max_row

class _Once:
    def __init__(self, value): self.value=value; self.calls=0
    def __fspath__(self):
        self.calls += 1
        if self.calls == 1: return self.value
        raise TypeError("twice")

def test_coerces_path_once_and_dependency_errors_forward(tmp_path):
    path = _Once(str(package(tmp_path / "once.xlsx")))
    assert len(read_worksheet_structure_semantics(path).worksheets) == 2 and path.calls == 1
    missing = package(tmp_path / "missing.xlsx", sheet_one_name="xl/worksheets/missing.xml")
    assert error(missing) == ("missing-internal-target", "xl/workbook.xml", "Target", "worksheets/first.xml")
