from __future__ import annotations

import pytest

from rns_import_server.opc_workbook_reader import OPCWorkbookError, read_opc_workbook
from tests.opc_workbook_fixture_factory import write_workbook


def test_reads_complete_namespace_aware_model(tmp_path):
    source = tmp_path / "semantic.xlsx"
    write_workbook(source)
    model = read_opc_workbook(str(source))
    assert model.contract_version == "opc-workbook-model-v1"
    assert [(item.part_name, item.extension) for item in model.content_types] == [(None, "rels"), (None, "xml"), ("xl/workbook.xml", None)]
    assert model.package_relationships[0].resolved_target == "xl/workbook.xml"
    assert [(item.name, item.sheet_id, item.state, item.part) for item in model.sheets] == [("First", 6, "visible", "xl/worksheets/sheet6.xml"), ("Second", 104, "hidden", "xl/worksheets/sheet104.xml")]
    first, second = model.sheets
    assert first.dimension == "A1:D10" and second.rows[0].index == 104
    assert first.columns[0].width == 22.5 and first.columns[0].hidden and first.columns[0].outline_level == 2
    row = first.rows[0]
    assert (row.index, row.height, row.hidden, row.outline_level, row.style_index) == (6, 18.5, True, 1, 1)
    shared, inline, dated, shared_formula = row.cells
    assert (shared.coordinate, shared.value, shared.shared_string_index) == ("A6", "shared text", 0)
    assert (inline.cell_type, inline.inline_string, inline.value) == ("inlineStr", "inline text", "inline text")
    assert dated.raw_value == "45292" and dated.style_fingerprint == model.styles[1].fingerprint
    assert (shared_formula.formula.kind, shared_formula.formula.shared_index, shared_formula.formula.ref, shared_formula.cached_value) == ("shared", 5, "D6:D10", "7")
    error, array_formula = first.rows[1].cells
    assert error.error == "#DIV/0!" and array_formula.formula.kind == "array" and array_formula.formula.ref == "B10:C10"
    style = model.styles[1]
    assert style.number_format == "yyyy-mm-dd" and style.font.name == "Arial" and style.fill.foreground_color == "rgb:FFFFFF00" and style.border.left == "thin"
    assert style.alignment == (("horizontal", "center"),) and style.protection == (("locked", "0"),)
    assert first.merges == ("A6:B6",) and first.auto_filter == "A6:D10"
    assert first.hyperlinks[0].location == "Second!A1" and first.hyperlinks[1].relationship.target == "https://example.test/x"
    assert [(item.name, item.local_sheet_id, item.hidden) for item in model.defined_names] == [("Global", None, False), ("Local", 1, True)]
    assert model.findings == (model.findings[0],) and model.findings[0].detail == "conditionalFormatting"
    assert len(model.part_digests) == 9 and all(len(digest) == 64 for _, digest in model.part_digests)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda parts: parts.__setitem__("xl/worksheets/../worksheets/sheet6.xml", parts["xl/worksheets/sheet6.xml"]), "duplicate-normalized-part"),
        (lambda parts: parts.__setitem__("xl/_rels/workbook.xml.rels", parts["xl/_rels/workbook.xml.rels"].replace("worksheets/sheet6.xml", "../outside.xml")), "part-traversal"),
        (lambda parts: parts.__setitem__("xl/_rels/workbook.xml.rels", parts["xl/_rels/workbook.xml.rels"].replace("worksheets/sheet104.xml", "worksheets/missing.xml")), "missing-relationship-target"),
        (lambda parts: parts.__setitem__("xl/worksheets/_rels/sheet6.xml.rels", parts["xl/worksheets/_rels/sheet6.xml.rels"].replace('TargetMode="External"', 'TargetMode="Broken"')), "malformed-relationship"),
    ],
)
def test_rejects_unsafe_or_malformed_package_mutations(tmp_path, mutate, code):
    source = tmp_path / "broken.xlsx"
    write_workbook(source, mutate)
    with pytest.raises(OPCWorkbookError) as raised:
        read_opc_workbook(str(source))
    assert raised.value.finding.code == code
