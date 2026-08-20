from __future__ import annotations
from dataclasses import FrozenInstanceError
import pytest
from rns_import_server.opc_workbook_topology import OPCWorkbookTopologyError
from rns_import_server.opc_worksheet_cell_reader import OPCWorksheetCellReaderError
from rns_import_server.opc_worksheet_structure_reader import OPCWorksheetStructureReaderError, read_worksheet_structure_semantics
from tests.opc_worksheet_structure_fixture_factory import package, worksheet

def error(path):
    with pytest.raises((OPCWorksheetStructureReaderError, OPCWorksheetCellReaderError, OPCWorkbookTopologyError)) as captured: read_worksheet_structure_semantics(path)
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


def test_preserves_cell_reader_row_lexicals_and_two_sheet_runtime_projection(tmp_path):
    rows = (
        '<row r="6" ht="1e1" s="+3" outlineLevel="-0"><c r="A6"><v>1</v></c></row>'
        '<row r="10" ht=".5" s="-0"><c r="A10"><v>2</v></c></row>'
        '<row r="104" ht="12.5"><c r="A104"><v>3</v></c></row>'
    )
    result = read_worksheet_structure_semantics(
        package(tmp_path / "lexical.xlsx", sheet_one=worksheet(rows=rows))
    )
    assert [(row.row, row.height, row.style_index, row.outline_level) for row in result.worksheets[0].rows] == [
        (6, 10.0, 3, 0), (10, 0.5, 0, None), (104, 12.5, None, None)
    ]
    assert [item.worksheet.name for item in result.worksheets] == ["Первый", "Второй"]


def test_rejects_namespace_collisions_and_non_row_major_merges(tmp_path):
    foreign_dimension = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:x="urn:foreign"><x:dimension ref="A6"/><sheetData>'
        '<row r="6"><c r="A6"><v>1</v></c></row></sheetData></worksheet>'
    ).encode()
    assert error(package(tmp_path / "foreign.xlsx", sheet_one=foreign_dimension)) == (
        "owned-worksheet-namespace-collision", "xl/worksheets/first.xml", "tag", "{urn:foreign}dimension"
    )
    empty_dimension = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<dimension ref="A6"/><sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData>'
        '<mergeCells count="2"><mergeCell ref="B10:C10"/><mergeCell ref="A6:B6"/></mergeCells></worksheet>'
    ).encode()
    assert error(package(tmp_path / "merge-order.xlsx", sheet_one=empty_dimension)) == (
        "out-of-order-merge-range", "xl/worksheets/first.xml", "ref", "A6:B6"
    )


def test_forwards_cell_boundary_xml_failures_without_retyping(tmp_path):
    malformed = b'<?xml version="1.0" encoding="UTF-16"?><worksheet>'
    with pytest.raises(OPCWorksheetCellReaderError) as captured:
        read_worksheet_structure_semantics(package(tmp_path / "encoding.xlsx", sheet_one=malformed))
    assert captured.value.as_tuple() == (
        "malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml"
    )


def test_requires_merge_count_and_preserves_bare_worksheet_root_attributes(tmp_path):
    root_attribute = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" custom="ok">'
        '<sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData></worksheet>'
    ).encode()
    assert read_worksheet_structure_semantics(
        package(tmp_path / "root-attribute.xlsx", sheet_one=root_attribute)
    ).worksheets[0].rows[0].row == 6
    missing_count = worksheet(merges='<mergeCells><mergeCell ref="A6:B6"/></mergeCells>')
    assert error(package(tmp_path / "missing-count.xlsx", sheet_one=missing_count)) == (
        "invalid-merge-count", "xl/worksheets/first.xml", "count", ""
    )


def test_rejects_empty_namespace_owned_name_collision(tmp_path):
    payload = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData>'
        '<autoFilter xmlns="" ref="A6"/></worksheet>'
    ).encode()
    assert error(package(tmp_path / "empty-namespace.xlsx", sheet_one=payload)) == (
        "owned-worksheet-namespace-collision", "xl/worksheets/first.xml", "tag", "autoFilter"
    )
