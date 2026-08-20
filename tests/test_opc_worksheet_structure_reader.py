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


@pytest.mark.parametrize(("leak", "tag"), [
    ('<mergeCell ref="A6:B6"/>', "mergeCell"),
    ('<row r="10"><c r="A10"><v>2</v></c></row>', "row"),
    ('<ext xmlns="urn:extension"><dimension xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ref="A6"/></ext>', "dimension"),
    ('<ext xmlns="urn:extension"><sheetData xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/></ext>', "sheetData"),
    ('<ext xmlns="urn:extension"><autoFilter xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ref="A6"/></ext>', "autoFilter"),
    ('<ext xmlns="urn:extension"><mergeCells xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0"/></ext>', "mergeCells"),
    ('<ext xmlns="urn:extension"><row xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" r="10"/></ext>', "row"),
    ('<ext xmlns="urn:extension"><mergeCell xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ref="A6:B6"/></ext>', "mergeCell"),
])
def test_rejects_owned_tags_outside_their_exact_legal_parent(tmp_path, leak, tag):
    payload = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData>' + leak + '</worksheet>'
    ).encode()
    assert error(package(tmp_path / "owned-parent.xlsx", sheet_one=payload)) == (
        "invalid-owned-worksheet-parent", "xl/worksheets/first.xml", "tag",
        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}" + tag,
    )


class _PathLikeFailure:
    def __init__(self, outcome):
        self.outcome = outcome

    def __fspath__(self):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.mark.parametrize(("value", "expected"), [
    (b"book.xlsx", ("invalid-package-path", "builtins.bytes", "path", "bytes")),
    (_PathLikeFailure(TypeError()), ("invalid-package-path", f"{__name__}._PathLikeFailure", "path", "TypeError")),
    (_PathLikeFailure(ValueError()), ("unreadable-package", f"{__name__}._PathLikeFailure", "path", "ValueError")),
    (_PathLikeFailure(OSError()), ("unreadable-package", f"{__name__}._PathLikeFailure", "path", "OSError")),
    # os.fspath itself rejects a non-string __fspath__ result as TypeError.
    (_PathLikeFailure(6), ("invalid-package-path", f"{__name__}._PathLikeFailure", "path", "TypeError")),
    ("bad\x00.xlsx", ("unreadable-package", "bad\x00.xlsx", "path", "embedded-nul")),
])
def test_pathlike_boundary_matrix_is_exact(value, expected):
    assert error(value) == expected


def test_member_alias_and_canonical_collision_are_distinct_and_typed(tmp_path):
    alias = package(tmp_path / "alias.xlsx", sheet_one_name="xl/worksheets/%66irst.xml")
    assert error(alias) == (
        "noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/%66irst.xml"
    )
    collision = package(
        tmp_path / "collision.xlsx", extra_members=(("xl/worksheets/%66irst.xml", worksheet()),)
    )
    assert error(collision) == (
        "duplicate-normalized-part", "xl/worksheets/first.xml", "name", "xl/worksheets/%66irst.xml"
    )
    missing = package(tmp_path / "missing-member.xlsx", sheet_one_name="xl/worksheets/missing.xml")
    assert error(missing) == (
        "missing-internal-target", "xl/workbook.xml", "Target", "worksheets/first.xml"
    )


@pytest.mark.parametrize(("payload", "expected"), [
    (
        b'<?xml version="1.0" encoding="UTF-16"?><worksheet>',
        ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml"),
    ),
    (
        b'<?xml version="1.0" encoding="utf-7"?><worksheet/>',
        ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding"),
    ),
    (b"<worksheet/>", ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "worksheet")),
    (
        b'<worksheet xmlns=""><sheetData/></worksheet>',
        ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "worksheet"),
    ),
    (
        b'<worksheet xmlns="urn:foreign"><sheetData/></worksheet>',
        ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "{urn:foreign}worksheet"),
    ),
])
def test_xml_boundary_failure_matrix_forwards_cell_error_unchanged(tmp_path, payload, expected):
    assert error(package(tmp_path / "xml-boundary.xlsx", sheet_one=payload)) == expected


def test_utf8_declaration_and_bom_are_accepted_before_structure_projection(tmp_path):
    payload = (
        b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>'
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        b'<sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData></worksheet>'
    )
    result = read_worksheet_structure_semantics(package(tmp_path / "utf8-bom.xlsx", sheet_one=payload))
    assert [(item.worksheet.worksheet_part.value, [row.row for row in item.rows]) for item in result.worksheets] == [
        ("xl/worksheets/first.xml", [6]), ("xl/worksheets/второй.xml", [6, 10, 104])
    ]


@pytest.mark.parametrize(("owner", "payload", "expected"), [
    ("worksheet", b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">bad<sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData></worksheet>', ("invalid-worksheet-content", "xl/worksheets/first.xml", "worksheet", "text")),
    ("dimension", worksheet(dimension='<dimension ref="A6">bad</dimension>'), ("invalid-worksheet-content", "xl/worksheets/first.xml", "dimension", "nested")),
    ("sheetData", worksheet(rows='<row r="6"><c r="A6"><v>1</v></c></row>bad'), ("invalid-worksheet-content", "xl/worksheets/first.xml", "sheetData", "tail")),
    ("row", worksheet(rows='<row r="6">bad<c r="A6"><v>1</v></c></row>'), ("invalid-worksheet-content", "xl/worksheets/first.xml", "row", "text")),
    ("autoFilter", worksheet(auto_filter='<autoFilter ref="A6">bad</autoFilter>'), ("invalid-auto-filter-content", "xl/worksheets/first.xml", "autoFilter", "nested")),
    ("mergeCells", worksheet(merges='<mergeCells count="0">bad</mergeCells>'), ("invalid-worksheet-content", "xl/worksheets/first.xml", "mergeCells", "text")),
    ("mergeCell", worksheet(merges='<mergeCells count="1"><mergeCell ref="A6">bad</mergeCell></mergeCells>'), ("invalid-worksheet-content", "xl/worksheets/first.xml", "mergeCell", "nested")),
])
def test_owned_content_owners_report_exact_matrix(tmp_path, owner, payload, expected):
    assert error(package(tmp_path / f"{owner}.xlsx", sheet_one=payload)) == expected


@pytest.mark.parametrize(("fragment", "expected"), [
    ('<dimension ref="A6" bad="x"/>', ("unknown-dimension-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    ('<sheetData bad="x"><row r="6"><c r="A6"><v>1</v></c></row></sheetData>', ("unknown-sheet-data-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    ('<autoFilter ref="A6" bad="x"/>', ("unknown-auto-filter-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    ('<mergeCells count="0" bad="x"/>', ("unknown-merge-cells-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    ('<mergeCells count="1"><mergeCell ref="A6" bad="x"/></mergeCells>', ("unknown-merge-cell-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
])
def test_owned_unknown_attribute_matrix_is_exact(tmp_path, fragment, expected):
    if fragment.startswith("<dimension"):
        payload = worksheet(dimension=fragment)
    elif fragment.startswith("<sheetData"):
        payload = (f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{fragment}</worksheet>').encode()
    elif fragment.startswith("<autoFilter"):
        payload = worksheet(auto_filter=fragment)
    else:
        payload = worksheet(merges=fragment)
    assert error(package(tmp_path / "unknown-owner.xlsx", sheet_one=payload)) == expected


@pytest.mark.parametrize(("namespace", "prefix", "detail"), [
    ("urn:foreign", "x:", "{urn:foreign}"),
    ("", "", ""),
])
@pytest.mark.parametrize("tag", ["dimension", "sheetData", "row", "autoFilter", "mergeCells", "mergeCell"])
def test_all_owned_local_names_reject_foreign_and_empty_namespace_collisions(tmp_path, namespace, prefix, detail, tag):
    declaration = ' xmlns:x="urn:foreign"' if namespace else ""
    reset = ' xmlns=""' if not namespace else ""
    payload = (
        f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"{declaration}>'
        f'<sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData>'
        f'<{prefix}{tag}{reset}/></worksheet>'
    ).encode()
    assert error(package(tmp_path / f"namespace-{tag}-{namespace or 'empty'}.xlsx", sheet_one=payload)) == (
        "owned-worksheet-namespace-collision", "xl/worksheets/first.xml", "tag", f"{detail}{tag}"
    )


@pytest.mark.parametrize(("reference", "expected"), [
    ("a6", ("A6", "A6", 6, 6, 1, 1)),
    ("$a$6:$xfd$1048576", ("A6", "XFD1048576", 6, 1048576, 1, 16384)),
    ("XFD1048576", ("XFD1048576", "XFD1048576", 1048576, 1048576, 16384, 16384)),
])
def test_a1_success_matrix_normalizes_exact_values(tmp_path, reference, expected):
    result = read_worksheet_structure_semantics(
        package(tmp_path / "a1-success.xlsx", sheet_one=worksheet(dimension=f'<dimension ref="{reference}"/>'))
    ).worksheets[0].dimension
    assert result is not None
    assert (result.start, result.end, result.min_row, result.max_row, result.min_column, result.max_column) == expected


@pytest.mark.parametrize("reference", [
    "", "A:A", "6:6", "Sheet1!A6", "Sheet1:Sheet2!A6", "A0", "A1048577", "XFE1",
    "AAAA1", "A6:B5", "B6:A7", "A6:B6:C6", "A6;B6", "A6:", ":A6", "A 6",
])
def test_complete_a1_failure_matrix_is_exact(tmp_path, reference):
    assert error(package(tmp_path / "a1-failure.xlsx", sheet_one=worksheet(dimension=f'<dimension ref="{reference}"/>'))) == (
        "invalid-a1-range", "xl/worksheets/first.xml", "ref", reference
    )


@pytest.mark.parametrize(("rows", "expected"), [
    ('<row r="6" ht="0" s="0" customHeight="0" customFormat="1" hidden="false" outlineLevel="0" collapsed="true"><c r="A6"><v>1</v></c></row>', (6, 0.0, 0, False, True, False, 0, True)),
    ('<row r="10" ht=" 1E2 " s="+4294967295" customHeight="1" customFormat="0" hidden="1" outlineLevel="7" collapsed="0"><c r="A10"><v>1</v></c></row>', (10, 100.0, 4294967295, True, False, True, 7, False)),
    ('<row r="104"><c r="A104"><v>1</v></c></row>', (104, None, None, None, None, None, None, None)),
])
def test_row_property_success_boundaries_preserve_all_fields(tmp_path, rows, expected):
    record = read_worksheet_structure_semantics(
        package(tmp_path / "row-success.xlsx", sheet_one=worksheet(rows=rows))
    ).worksheets[0].rows[0]
    assert (record.row, record.height, record.style_index, record.custom_height, record.custom_format, record.hidden, record.outline_level, record.collapsed) == expected


@pytest.mark.parametrize(("row", "expected"), [
    ('<row><c r="A6"><v>1</v></c></row>', ("invalid-row", "xl/worksheets/first.xml", "r", "")),
    ('<row r="0"><c r="A1"><v>1</v></c></row>', ("invalid-row", "xl/worksheets/first.xml", "r", "0")),
    ('<row r="1048577"><c r="A1048577"><v>1</v></c></row>', ("invalid-row", "xl/worksheets/first.xml", "r", "1048577")),
    ('<row r="6" s="4294967296"><c r="A6"><v>1</v></c></row>', ("invalid-row-property", "xl/worksheets/first.xml", "s", "4294967296")),
    ('<row r="6" outlineLevel="8"><c r="A6"><v>1</v></c></row>', ("invalid-row-property", "xl/worksheets/first.xml", "outlineLevel", "8")),
    ('<row r="6" hidden="yes"><c r="A6"><v>1</v></c></row>', ("invalid-row-property", "xl/worksheets/first.xml", "hidden", "yes")),
    ('<row r="6" nope="x"><c r="A6"><v>1</v></c></row>', ("unknown-row-attribute", "xl/worksheets/first.xml", "attribute", "nope")),
])
def test_row_failure_boundaries_are_exact(tmp_path, row, expected):
    assert error(package(tmp_path / "row-failure.xlsx", sheet_one=worksheet(rows=row))) == expected


def test_merge_matrix_count_order_and_normalized_duplicate_are_exact(tmp_path):
    cases = [
        ('<mergeCells count=""><mergeCell ref="A6"/></mergeCells>', ("invalid-merge-count", "xl/worksheets/first.xml", "count", "")),
        ('<mergeCells count="4294967296"/>', ("invalid-merge-count", "xl/worksheets/first.xml", "count", "4294967296")),
        ('<mergeCells count="1"><mergeCell ref="A6:B6"/><mergeCell ref="B10:C10"/></mergeCells>', ("merge-count-mismatch", "xl/worksheets/first.xml", "count", "1")),
        ('<mergeCells count="2"><mergeCell ref="B10:C10"/><mergeCell ref="A6:B6"/></mergeCells>', ("out-of-order-merge-range", "xl/worksheets/first.xml", "ref", "A6:B6")),
        ('<mergeCells count="2"><mergeCell ref="$a$6:$b$6"/><mergeCell ref="A6:B6"/></mergeCells>', ("duplicate-merge-range", "xl/worksheets/first.xml", "ref", "A6:B6")),
        ('<mergeCells count="1"><mergeCell/></mergeCells>', ("invalid-a1-range", "xl/worksheets/first.xml", "ref", "")),
        ('<mergeCells count="1"><bogus/></mergeCells>', ("invalid-merge-cells-child", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}bogus")),
    ]
    for index, (merges, expected) in enumerate(cases):
        assert error(package(tmp_path / f"merge-{index}.xlsx", sheet_one=worksheet(merges=merges))) == expected


def test_second_sheet_values_are_independent_and_ordered(tmp_path):
    second = worksheet(
        dimension='<dimension ref="B10:XFD1048576"/>',
        rows='<row r="10"><c r="B10"><v>2</v></c></row><row r="1048576"><c r="XFD1048576"><v>3</v></c></row>',
        auto_filter='<autoFilter ref="B10:XFD1048576"/>',
        merges='<mergeCells count="1"><mergeCell ref="B10:C10"/></mergeCells>',
    )
    result = read_worksheet_structure_semantics(package(tmp_path / "second.xlsx", sheet_two=second))
    assert [(item.worksheet.name, item.dimension.start if item.dimension else None, [row.row for row in item.rows], [(merge.start, merge.end) for merge in item.merges], item.auto_filter.reference.end if item.auto_filter else None) for item in result.worksheets] == [
        ("Первый", "A6", [6, 10, 104], [("A6", "B6"), ("A10", "C104")], "C104"),
        ("Второй", "B10", [10, 1048576], [("B10", "C10")], "XFD1048576"),
    ]


def test_dependency_precedence_is_topology_then_cell_then_structure(tmp_path):
    topology_first = package(tmp_path / "topology-first.xlsx", sheet_one_name="xl/worksheets/missing.xml")
    assert error(topology_first) == (
        "missing-internal-target", "xl/workbook.xml", "Target", "worksheets/first.xml"
    )
    cell_first = worksheet(rows='<row r="10"><c r="A10"><v>1</v></c></row><row r="6"><c r="A6"><v>1</v></c></row>', merges='<mergeCells count="bad"/>')
    assert error(package(tmp_path / "cell-first.xlsx", sheet_one=cell_first)) == (
        "out-of-order-row", "xl/worksheets/first.xml", "r", "6"
    )
    structure_last = worksheet(rows='<row r="6"><c r="A6"><v>1</v></c></row>', merges='<mergeCells count="bad"/>')
    assert error(package(tmp_path / "structure-last.xlsx", sheet_one=structure_last)) == (
        "invalid-merge-count", "xl/worksheets/first.xml", "count", "bad"
    )
