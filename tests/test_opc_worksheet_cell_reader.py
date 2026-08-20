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
