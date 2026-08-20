from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from rns_import_server.opc_worksheet_cell_reader import OPCWorksheetCellReaderError, read_worksheet_cell_semantics
from tests.opc_worksheet_cell_fixture_factory import OFFICE_REL_NS, package, relationship, worksheet


def error(path):
    with pytest.raises(OPCWorksheetCellReaderError) as captured:
        read_worksheet_cell_semantics(path)
    return captured.value.as_tuple()


def test_reads_immutable_ordered_cells_formulae_and_hyperlinks(tmp_path):
    links = ('<hyperlinks><hyperlink ref="A6" r:id="external" display="Сайт" tooltip="Открыть"/>'
             '<hyperlink ref="B10" r:id="internal"/><hyperlink ref="C104" location="Второй!A6"/></hyperlinks>')
    sheet = worksheet('<row r="6"><c r="A6"><v>7</v></c></row>'
                      '<row r="10"><c r="B10" t="inlineStr"><is><t>текст</t></is></c></row>'
                      '<row r="104"><c r="C104"><f t="shared" si="3" ref="C104:D104">SUM(A6)</f><v>7</v></c>'
                      '<c r="D104"><f t="array" ref="D104:E104">A6</f><v>7</v></c></row>', links)
    rels = (relationship("external", f"{OFFICE_REL_NS}/hyperlink", "https://example.test/цель", "External") +
            relationship("internal", f"{OFFICE_REL_NS}/hyperlink", "второй.xml"))
    result = read_worksheet_cell_semantics(package(tmp_path / "ok.xlsx", sheet_one=sheet, sheet_one_rels=rels))
    first = result.worksheets[0]
    assert [cell.coordinate for cell in first.cells] == ["A6", "B10", "C104", "D104"]
    assert first.cells[1].inline_text == "текст"
    assert first.cells[2].formula and first.cells[2].formula.shared_index == 3
    assert [(item.ref, item.target_mode, item.target, item.resolved_target.value if item.resolved_target else None) for item in first.hyperlinks] == [("A6", "External", "https://example.test/цель", None), ("B10", "Internal", "второй.xml", "xl/worksheets/второй.xml"), ("C104", None, None, None)]
    with pytest.raises(FrozenInstanceError): first.cells[0].coordinate = "Z1"


@pytest.mark.parametrize(("sheet", "expected"), [
    (b"<worksheet/>", ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "worksheet")),
    (b'<?xml version="1.0" encoding="utf-7"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (worksheet('<row r="6"><c r="A7"><v>1</v></c></row>'), ("cell-row-mismatch", "xl/worksheets/first.xml", "r", "A7")),
    (worksheet('<row r="10"><c r="B10"><v>1</v></c></row><row r="6"><c r="A6"><v>1</v></c></row>'), ("out-of-order-row", "xl/worksheets/first.xml", "r", "6")),
    (worksheet('<row r="6"><c r="B6"><v>1</v></c><c r="A6"><v>1</v></c></row>'), ("out-of-order-cell", "xl/worksheets/first.xml", "r", "A6")),
    (worksheet('<row r="6"><c r="A6" t="inlineStr"><v>1</v></c></row>'), ("invalid-cell-payload", "xl/worksheets/first.xml", "t", "inlineStr")),
    (worksheet('<row r="6"><c r="A6" t="s"><v>x</v></c></row>'), ("invalid-shared-string-index", "xl/worksheets/first.xml", "v", "x")),
    (worksheet('<row r="6"><c r="A6"><f t="dataTable">A1</f><v>1</v></c></row>'), ("unsupported-formula-kind", "xl/worksheets/first.xml", "t", "dataTable")),
])
def test_rejects_strict_cell_defects(tmp_path, sheet, expected):
    assert error(package(tmp_path / "bad.xlsx", sheet_one=sheet)) == expected


def test_rejects_hyperlink_mapping_and_duplicates(tmp_path):
    missing = worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" r:id="gone"/></hyperlinks>')
    assert error(package(tmp_path / "missing.xlsx", sheet_one=missing)) == ("missing-hyperlink-relationship", "xl/worksheets/first.xml", "r:id", "gone")
    wrong = worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" r:id="x"/></hyperlinks>')
    assert error(package(tmp_path / "wrong.xlsx", sheet_one=wrong, sheet_one_rels=relationship("x", "https://example.test/no", "https://x", "External"))) == ("non-hyperlink-relationship", "xl/worksheets/first.xml", "r:id", "x")
    duplicate = worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" location="a"/><hyperlink ref="A6" location="b"/></hyperlinks>')
    assert error(package(tmp_path / "duplicate.xlsx", sheet_one=duplicate)) == ("duplicate-hyperlink-ref", "xl/worksheets/first.xml", "ref", "A6")


class _StatefulPath:
    def __init__(self, value): self.value = value; self.calls = 0
    def __fspath__(self):
        self.calls += 1
        if self.calls == 1: return self.value
        raise TypeError("called twice")


def test_coerces_pathlike_once(tmp_path):
    path = _StatefulPath(str(package(tmp_path / "one.xlsx")))
    assert len(read_worksheet_cell_semantics(path).worksheets) == 2
    assert path.calls == 1


@pytest.mark.parametrize(("sheet", "expected"), [
    (worksheet('<row r="' + "9" * 5000 + '"><c r="A1"><v>1</v></c></row>'), ("invalid-row", "xl/worksheets/first.xml", "r", "9" * 5000)),
    (worksheet('<row r="6"><c r="A6" t="s"><v>' + "9" * 5000 + '</v></c></row>'), ("invalid-shared-string-index", "xl/worksheets/first.xml", "v", "9" * 5000)),
    (worksheet('<row r="6"><c r="A6"><f t="shared" si="' + "9" * 5000 + '">A1</f></c></row>'), ("invalid-shared-formula-index", "xl/worksheets/first.xml", "si", "9" * 5000)),
    (worksheet('<row r="6"><c r="A6"><v>1</v><f>A1</f></c></row>'), ("invalid-cell-child-order", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f")),
])
def test_bounds_and_cell_xml_order_are_typed(tmp_path, sheet, expected):
    assert error(package(tmp_path / "bounds.xlsx", sheet_one=sheet)) == expected


def test_accepts_excel_metadata_preserved_text_and_uncached_formula(tmp_path):
    sheet = worksheet('<row r="6" spans="1:3"><c r="A6" s="0" t="inlineStr"><is><t xml:space="preserve"> x </t></is></c>'
                      '<c r="B6"><f>NOW()</f></c><c r="C6" t="b"><v>1</v></c><c r="D6" t="d"><v>2026-01-01</v></c>'
                      '<c r="E6" t="e"><v>#N/A</v></c><c r="F6" t="str"><v>result</v></c></row>')
    cells = read_worksheet_cell_semantics(package(tmp_path / "metadata.xlsx", sheet_one=sheet)).worksheets[0].cells
    assert [cell.cell_type for cell in cells] == ["inlineStr", "", "b", "d", "e", "str"]
    assert cells[0].inline_text == " x " and cells[1].formula and cells[1].value is None


def test_rejects_mixed_nested_hyperlink_and_formula_payload_matrix(tmp_path):
    nested = worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" location="a"><x/></hyperlink></hyperlinks>')
    assert error(package(tmp_path / "nested.xlsx", sheet_one=nested)) == ("invalid-hyperlink-content", "xl/worksheets/first.xml", "content", "nested")
    inline_formula = worksheet('<row r="6"><c r="A6" t="inlineStr"><f>A1</f><is><t>x</t></is></c></row>')
    assert error(package(tmp_path / "inline-formula.xlsx", sheet_one=inline_formula)) == ("invalid-formula-payload", "xl/worksheets/first.xml", "t", "inlineStr")
    shared_formula = worksheet('<row r="6"><c r="A6" t="s"><f>A1</f><v>1</v></c></row>')
    assert error(package(tmp_path / "shared-formula.xlsx", sheet_one=shared_formula)) == ("invalid-formula-payload", "xl/worksheets/first.xml", "t", "s")


def test_rejects_row_text_and_cell_tail_before_cell_consumption(tmp_path):
    text = worksheet('<row r="6">bad<c r="A6"><v>1</v></c></row>')
    assert error(package(tmp_path / "row-text.xlsx", sheet_one=text)) == ("invalid-worksheet-content", "xl/worksheets/first.xml", "row", "text")
    tail = worksheet('<row r="6"><c r="A6"><v>1</v></c>bad<c r="B6"><v>2</v></c></row>')
    assert error(package(tmp_path / "cell-tail.xlsx", sheet_one=tail)) == ("invalid-worksheet-content", "xl/worksheets/first.xml", "row", "tail")


@pytest.mark.parametrize(("second", "expected"), [
    ('<c r="A6"><v>2</v></c>', ("duplicate-cell-coordinate", "xl/worksheets/first.xml", "r", "A6")),
    ('<c r="A6"><v>2</v>bad</c>', ("invalid-cell-content", "xl/worksheets/first.xml", "tail", "A6")),
    ('<c r="A6"><bad/></c>', ("invalid-cell-child", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}bad")),
])
def test_duplicate_coordinate_is_checked_after_current_cell_validation(tmp_path, second, expected):
    sheet = worksheet(f'<row r="6"><c r="A6"><v>1</v></c>{second}</row>')
    assert error(package(tmp_path / "precedence.xlsx", sheet_one=sheet)) == expected


@pytest.mark.parametrize(("sheet", "expected"), [
    (worksheet('<row r="1"><c r="A0"><v>1</v></c></row>'), ("invalid-a1-reference", "xl/worksheets/first.xml", "r", "A0")),
    (worksheet('<row r="1"><c r="XFE1"><v>1</v></c></row>'), ("invalid-a1-reference", "xl/worksheets/first.xml", "r", "XFE1")),
    (worksheet('<row r="1048576"><c r="XFD1048576"><v>1</v></c></row>'), None),
    (worksheet('<row r="6"><c r="A6"><v>1</v></c><c r="A6"><v>2</v></c></row>'), ("duplicate-cell-coordinate", "xl/worksheets/first.xml", "r", "A6")),
    (worksheet('<row r="6"><c r="A6" t="inlineStr"><is><r><t>x</t></r></is></c></row>'), ("invalid-inline-string", "xl/worksheets/first.xml", "is", "structure")),
])
def test_a1_boundaries_duplicates_and_rich_inline_are_frozen(tmp_path, sheet, expected):
    path = package(tmp_path / "a1.xlsx", sheet_one=sheet)
    if expected is None:
        assert [cell.coordinate for cell in read_worksheet_cell_semantics(path).worksheets[0].cells] == ["XFD1048576"]
    else:
        assert error(path) == expected


def test_hyperlink_anchor_attribute_and_relationship_failures_are_typed(tmp_path):
    base = '<row r="6"><c r="A6"><v>1</v></c><c r="B6"><v>2</v></c></row>'
    neither = worksheet(base, '<hyperlinks><hyperlink ref="A6"/></hyperlinks>')
    assert error(package(tmp_path / "neither.xlsx", sheet_one=neither)) == ("invalid-hyperlink-anchor", "xl/worksheets/first.xml", "anchor", "A6")
    both = worksheet(base, '<hyperlinks><hyperlink ref="A6" r:id="x" location="here"/></hyperlinks>')
    assert error(package(tmp_path / "both.xlsx", sheet_one=both, sheet_one_rels=relationship("x", f"{OFFICE_REL_NS}/hyperlink", "https://x", "External"))) == ("invalid-hyperlink-anchor", "xl/worksheets/first.xml", "anchor", "A6")
    blank = worksheet(base, '<hyperlinks><hyperlink ref="A6" location="x" display=" "/></hyperlinks>')
    assert error(package(tmp_path / "blank.xlsx", sheet_one=blank)) == ("blank-hyperlink-attribute", "xl/worksheets/first.xml", "display", "")
    duplicate_id = worksheet(base, '<hyperlinks><hyperlink ref="A6" r:id="x"/><hyperlink ref="B6" r:id="x"/></hyperlinks>')
    rels = relationship("x", f"{OFFICE_REL_NS}/hyperlink", "https://x", "External")
    assert error(package(tmp_path / "duplicate-id.xlsx", sheet_one=duplicate_id, sheet_one_rels=rels)) == ("duplicate-hyperlink-relationship-id", "xl/worksheets/first.xml", "r:id", "x")
    bad_ref = worksheet(base, '<hyperlinks><hyperlink ref="A6:A5" location="x"/></hyperlinks>')
    assert error(package(tmp_path / "bad-ref.xlsx", sheet_one=bad_ref)) == ("invalid-a1-reference", "xl/worksheets/first.xml", "ref", "A6:A5")


class _BadPath:
    def __init__(self, exception): self.exception = exception
    def __fspath__(self): raise self.exception


@pytest.mark.parametrize(("value", "expected"), [
    (b"book.xlsx", ("invalid-package-path", "builtins.bytes", "path", "bytes")),
    (_BadPath(TypeError()), ("invalid-package-path", f"{__name__}._BadPath", "path", "TypeError")),
    (_BadPath(ValueError()), ("unreadable-package", f"{__name__}._BadPath", "path", "ValueError")),
    ("bad\x00.xlsx", ("unreadable-package", "bad\x00.xlsx", "path", "embedded-nul")),
])
def test_pathlike_failures_are_one_boundary_tuples(value, expected):
    assert error(value) == expected


def test_graph_forwarded_missing_and_canonical_alias_members_are_deterministic(tmp_path):
    missing = package(tmp_path / "missing.xlsx", sheet_one_name="xl/worksheets/missing.xml")
    # The fixture relationship still targets first.xml, so graph construction rejects it before XML reading.
    assert error(missing) == ("missing-internal-target", "xl/workbook.xml", "Target", "worksheets/first.xml")
    alias = package(tmp_path / "alias.xlsx", sheet_one_name="xl/worksheets/%66irst.xml")
    assert read_worksheet_cell_semantics(alias).worksheets[0].worksheet.worksheet_part.value == "xl/worksheets/first.xml"


@pytest.mark.parametrize(("sheet", "rels", "expected"), [
    (b'<worksheet xmlns="urn:wrong"><sheetData/></worksheet>', "", ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "{urn:wrong}worksheet")),
    (b'<worksheet', "", ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" location=" "/></hyperlinks>'), "", ("blank-hyperlink-attribute", "xl/worksheets/first.xml", "location", "")),
    (worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" r:id=" "/></hyperlinks>'), "", ("blank-hyperlink-attribute", "xl/worksheets/first.xml", "r:id", "")),
    (worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" location="x" tooltip=" "/></hyperlinks>'), "", ("blank-hyperlink-attribute", "xl/worksheets/first.xml", "tooltip", "")),
    (worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" r:id="x"/></hyperlinks>'), relationship("x", f"{OFFICE_REL_NS}/hyperlink", "https://x", "Bad"), ("invalid-target-mode", "xl/worksheets/first.xml", "TargetMode", "Bad")),
    (worksheet('<row r="6"><c r="A6"><v>1</v></c></row>', '<hyperlinks><hyperlink ref="A6" r:id="x"/></hyperlinks>'), relationship("x", f"{OFFICE_REL_NS}/hyperlink", "missing.xml"), ("missing-internal-target", "xl/worksheets/first.xml", "Target", "missing.xml")),
])
def test_malformed_and_hyperlink_boundary_failures_are_frozen(tmp_path, sheet, rels, expected):
    assert error(package(tmp_path / "negative.xlsx", sheet_one=sheet, sheet_one_rels=rels)) == expected
