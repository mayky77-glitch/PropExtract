from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

import rns_import_server.opc_worksheet_x14_cf_reader as reader
from rns_import_server.opc_workbook_topology import OPCWorkbookTopologyError
from rns_import_server.opc_worksheet_x14_cf_reader import OPCWorksheetX14CfReaderError, read_worksheet_x14_cf_envelope
from tests.opc_worksheet_x14_cf_fixture_factory import URI, package, worksheet


def envelope(containers: str) -> str:
    return f'<extLst><ext uri="{URI}"><x14:conditionalFormattings>{containers}</x14:conditionalFormattings></ext></extLst>'


def container(row: int, priority: int, stop: str = "true") -> str:
    return (f'<x14:conditionalFormatting><x14:cfRule type="expression" priority="{priority}" stopIfTrue="{stop}" id="id-{row}">'
            f'<xm:f> formula {row} </xm:f><x14:dxf><font/><fill/></x14:dxf></x14:cfRule><xm:sqref> raw {row} </xm:sqref></x14:conditionalFormatting>')


def error(path):
    with pytest.raises(OPCWorksheetX14CfReaderError) as captured:
        read_worksheet_x14_cf_envelope(path)
    return captured.value.as_tuple()


def test_full_projection_identity_ancestry_and_immutable_records(tmp_path):
    body = envelope(container(6, 10, "0") + container(10, 3, "false") + container(104, 7, "1"))
    result = read_worksheet_x14_cf_envelope(package(tmp_path / "ok.xlsx", sheet_one=worksheet(body)))
    first = result.worksheets[0]
    assert tuple(field.name for field in fields(reader.X14CfRuleEnvelope)) == (
        "owner_path", "document_order", "type", "priority", "stop_if_true", "rule_id", "formula", "has_inline_dxf",
    )
    assert tuple(field.name for field in fields(reader.X14CfContainerEnvelope)) == ("owner_path", "sqref_text", "rules")
    assert tuple(field.name for field in fields(reader.WorksheetX14CfEnvelope)) == ("worksheet", "containers")
    assert tuple(field.name for field in fields(reader.WorkbookX14CfEnvelope)) == ("worksheets",)
    assert tuple(field.name for field in fields(reader.OPCWorksheetX14CfReaderError)) == ("code", "subject", "field", "detail")
    assert [rule.document_order for item in first.containers for rule in item.rules] == [1, 2, 3]
    assert [rule.priority for item in first.containers for rule in item.rules] == [10, 3, 7]
    assert first.containers[0].sqref_text == " raw 6 "
    assert first.containers[0].rules[0].formula == " formula 6 "
    assert first.worksheet is result.worksheets[0].worksheet
    assert first.containers[0].owner_path.endswith("conditionalFormatting[1]")
    assert "/cfRule[1]" in first.containers[0].rules[0].owner_path
    assert asdict(result)["worksheets"][0]["containers"][0]["rules"][0]["has_inline_dxf"] is True
    with pytest.raises(FrozenInstanceError):
        first.containers = ()
    with pytest.raises(FrozenInstanceError):
        first.containers[0].rules[0].priority = 1
    with pytest.raises(FrozenInstanceError):
        result.worksheets = ()
    with pytest.raises(FrozenInstanceError):
        first.worksheet = None


@pytest.mark.parametrize(("body", "expected"), [
    ("<x14:conditionalFormattings/>", ("invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}conditionalFormattings")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>').replace(URI, URI.lower()), ("unsupported-x14-cf-extension-uri", "xl/worksheets/first.xml", "uri", URI.lower())),
    (envelope('<x:conditionalFormatting xmlns:x="urn:foreign"/>'), ("x14-cf-namespace-collision", "xl/worksheets/first.xml", "tag", "{urn:foreign}conditionalFormatting")),
    (envelope('<x14:conditionalFormatting bad="x"/>'), ("unknown-x14-cf-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref> </xm:sqref></x14:conditionalFormatting>'), ("invalid-x14-cf-sqref", "xl/worksheets/first.xml", "sqref", "blank")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="maybe" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("invalid-x14-cf-boolean", "xl/worksheets/first.xml", "stopIfTrue", "maybe")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="cellIs" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("unsupported-x14-cf-rule-type", "xl/worksheets/first.xml", "type", "cellIs")),
])
def test_owned_boundary_errors(tmp_path, body, expected):
    assert error(package(tmp_path / "bad.xlsx", sheet_one=worksheet(body))) == expected


@pytest.mark.parametrize(("mutation", "expected"), [
    ('<xm:sqref>A6</xm:sqref><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule>', ("invalid-x14-cf-order", "xl/worksheets/first.xml", "conditionalFormatting", "cfRule/sqref")),
    ('<x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><x14:dxf/><xm:f>x</xm:f></x14:cfRule><xm:sqref>A6</xm:sqref>', ("invalid-x14-cf-order", "xl/worksheets/first.xml", "cfRule", "f/dxf")),
    ('<x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f></x14:cfRule><xm:sqref>A6</xm:sqref>', ("invalid-x14-cf-cardinality", "xl/worksheets/first.xml", "cfRule", "f/dxf")),
])
def test_order_and_cardinality(tmp_path, mutation, expected):
    assert error(package(tmp_path / "order.xlsx", sheet_one=worksheet(envelope(f'<x14:conditionalFormatting>{mutation}</x14:conditionalFormatting>')))) == expected


def test_duplicate_priority_and_sibling_x14_dv_coexist(tmp_path):
    body = envelope(container(6, 1) + container(10, 1)) + '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations/></ext></extLst>'
    assert error(package(tmp_path / "duplicate.xlsx", sheet_one=worksheet(body))) == (
        "duplicate-x14-cf-priority", "xl/worksheets/first.xml", "priority", "1",
    )
    valid = envelope(container(6, 1)) + '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations/></ext></extLst>'
    assert len(read_worksheet_x14_cf_envelope(package(tmp_path / "dv.xlsx", sheet_one=worksheet(valid))).worksheets[0].containers) == 1


def test_two_sheet_corpus_preserves_rows_orders_and_full_projection(tmp_path):
    first = envelope(container(6, 10, "0") + container(10, 3, "false"))
    second = envelope(container(104, 7, "1"))
    result = read_worksheet_x14_cf_envelope(package(
        tmp_path / "two-sheet.xlsx", sheet_one=worksheet(first), sheet_two=worksheet(second),
    ))
    assert asdict(result) == {
        "worksheets": (
            {"worksheet": {"name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one", "worksheet_part": {"value": "xl/worksheets/first.xml"}}, "containers": (
                {"owner_path": "xl/worksheets/first.xml/worksheet/extLst/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "sqref_text": " raw 6 ", "rules": ({"owner_path": "xl/worksheets/first.xml/worksheet/extLst/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]", "document_order": 1, "type": "expression", "priority": 10, "stop_if_true": False, "rule_id": "id-6", "formula": " formula 6 ", "has_inline_dxf": True},)},
                {"owner_path": "xl/worksheets/first.xml/worksheet/extLst/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]", "sqref_text": " raw 10 ", "rules": ({"owner_path": "xl/worksheets/first.xml/worksheet/extLst/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]/cfRule[1]", "document_order": 2, "type": "expression", "priority": 3, "stop_if_true": False, "rule_id": "id-10", "formula": " formula 10 ", "has_inline_dxf": True},)},
            )},
            {"worksheet": {"name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two", "worksheet_part": {"value": "xl/worksheets/второй.xml"}}, "containers": (
                {"owner_path": "xl/worksheets/второй.xml/worksheet/extLst/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "sqref_text": " raw 104 ", "rules": ({"owner_path": "xl/worksheets/второй.xml/worksheet/extLst/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]", "document_order": 1, "type": "expression", "priority": 7, "stop_if_true": True, "rule_id": "id-104", "formula": " formula 104 ", "has_inline_dxf": True},)},
            )},
        ),
    }


def test_xm_content_in_sibling_x14_dv_is_unowned(tmp_path):
    dv = ('<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations>'
          '<x14:dataValidation><xm:f>not-cf</xm:f><xm:sqref>not-cf</xm:sqref></x14:dataValidation>'
          '</x14:dataValidations></ext></extLst>')
    result = read_worksheet_x14_cf_envelope(package(tmp_path / "sibling.xlsx", sheet_one=worksheet(dv)))
    assert result.worksheets[0].containers == ()


@pytest.mark.parametrize(("body", "expected"), [
    ('<extLst><ext uri="' + URI + '"/></extLst>', ("invalid-x14-cf-cardinality", "xl/worksheets/first.xml", "ext", "conditionalFormattings")),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings/></ext>'
     '<ext uri="' + URI + '"><x14:conditionalFormattings/></ext></extLst>', ("invalid-x14-cf-cardinality", "xl/worksheets/first.xml", "conditionalFormattings", "conditionalFormatting")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="\u00a01\u00a0" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("invalid-x14-cf-priority", "xl/worksheets/first.xml", "priority", "\u00a01\u00a0")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="999999999999999999999999999999999999999" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("invalid-x14-cf-priority", "xl/worksheets/first.xml", "priority", "999999999999999999999999999999999999999")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf><border/></x14:dxf></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("unknown-x14-cf-child", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}border")),
])
def test_p6_exact_boundaries(tmp_path, body, expected):
    assert error(package(tmp_path / "p6.xlsx", sheet_one=worksheet(body))) == expected


@pytest.mark.parametrize(("body", "expected"), [
    ('<extLst bad="x"><ext uri="' + URI + '"><x14:conditionalFormattings/></ext></extLst>', ("unknown-x14-cf-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings bad="x"/></ext></extLst>', ("unknown-x14-cf-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings><bad/></x14:conditionalFormattings></ext></extLst>', ("unknown-x14-cf-child", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}bad")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="0" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("invalid-x14-cf-priority", "xl/worksheets/first.xml", "priority", "0")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id=" "><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("invalid-x14-cf-id", "xl/worksheets/first.xml", "id", " ")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("invalid-x14-cf-cardinality", "xl/worksheets/first.xml", "cfRule", "f/dxf")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f bad="x">x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("unknown-x14-cf-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf bad="x"/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("unknown-x14-cf-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf><x14:bad/></x14:dxf></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), ("unknown-x14-cf-child", "xl/worksheets/first.xml", "tag", "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}bad")),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref bad="x">A6</xm:sqref></x14:conditionalFormatting>'), ("unknown-x14-cf-attribute", "xl/worksheets/first.xml", "attribute", "bad")),
])
def test_adversarial_semantic_matrix(tmp_path, body, expected):
    assert error(package(tmp_path / "matrix.xlsx", sheet_one=worksheet(body))) == expected


@pytest.mark.parametrize(("payload", "expected"), [
    (b"", ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b"<notWorksheet/>", ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "notWorksheet")),
])
def test_xml_and_root_boundaries(tmp_path, payload, expected):
    assert error(package(tmp_path / "xml.xlsx", sheet_one=payload)) == expected


def test_exact_parse_count_per_topology_worksheet(monkeypatch, tmp_path):
    original = reader.ET.fromstring
    calls = []

    def counted(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(reader.ET, "fromstring", counted)
    read_worksheet_x14_cf_envelope(package(tmp_path / "count.xlsx", sheet_one=worksheet(envelope(container(6, 1)))))
    assert sum(payload.startswith(b"<worksheet") for payload in calls) == 2


def test_exact_parse_count_stops_at_the_raising_worksheet(monkeypatch, tmp_path):
    original = reader.ET.fromstring
    calls = []

    def counted(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(reader.ET, "fromstring", counted)
    assert error(package(tmp_path / "parse-raises.xlsx", sheet_one=b"")) == (
        "malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml",
    )
    assert sum(payload == b"" for payload in calls) == 1


@pytest.mark.parametrize(("body", "expected"), [
    ('<extLst>text<ext uri="' + URI + '"><x14:conditionalFormattings/></ext></extLst>', ("invalid-x14-cf-content", "xl/worksheets/first.xml", "extLst", "text")),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings/></ext>tail</extLst>', ("invalid-x14-cf-content", "xl/worksheets/first.xml", "extLst", "tail")),
    ('<extLst><ext uri="' + URI + '">text<x14:conditionalFormattings/></ext></extLst>', ("invalid-x14-cf-content", "xl/worksheets/first.xml", "ext", "text")),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings/>tail</ext></extLst>', ("invalid-x14-cf-content", "xl/worksheets/first.xml", "ext", "tail")),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings>text</x14:conditionalFormattings></ext></extLst>', ("invalid-x14-cf-content", "xl/worksheets/first.xml", "conditionalFormattings", "text")),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings><x14:conditionalFormatting/>tail</x14:conditionalFormattings></ext></extLst>', ("invalid-x14-cf-content", "xl/worksheets/first.xml", "conditionalFormattings", "tail")),
])
def test_owned_extension_mixed_content_is_exact_and_document_ordered(tmp_path, body, expected):
    assert error(package(tmp_path / "mixed.xlsx", sheet_one=worksheet(body))) == expected


def test_collision_walk_is_ordered_at_owned_depths_and_skips_sibling_dv_subtrees(tmp_path):
    foreign_before_misplaced = (
        '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><foreign:conditionalFormattings '
        'xmlns:foreign="urn:foreign"/></ext></extLst><x14:conditionalFormattings/>'
    )
    assert error(package(tmp_path / "collision-first.xlsx", sheet_one=worksheet(foreign_before_misplaced))) == (
        "x14-cf-namespace-collision", "xl/worksheets/first.xml", "tag", "{urn:foreign}conditionalFormattings",
    )
    empty_before_misplaced = (
        '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><conditionalFormattings/>'
        '</ext></extLst><x14:conditionalFormattings/>'
    )
    assert error(package(tmp_path / "empty-first.xlsx", sheet_one=worksheet(empty_before_misplaced))) == (
        "x14-cf-namespace-collision", "xl/worksheets/first.xml", "tag",
        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}conditionalFormattings",
    )
    sibling_dv = (
        '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations>'
        '<x14:dataValidation><foreign:conditionalFormattings xmlns:foreign="urn:foreign"/>'
        '</x14:dataValidation></x14:dataValidations></ext></extLst>'
    )
    assert asdict(read_worksheet_x14_cf_envelope(package(tmp_path / "dv-subtree.xlsx", sheet_one=worksheet(sibling_dv)))) == {
        "worksheets": (
            {"worksheet": {"name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one", "worksheet_part": {"value": "xl/worksheets/first.xml"}}, "containers": ()},
            {"worksheet": {"name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two", "worksheet_part": {"value": "xl/worksheets/второй.xml"}}, "containers": ()},
        ),
    }


class _CountedPathLike:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __fspath__(self):
        self.calls += 1
        return self.result


def test_pathlike_is_coerced_once_for_success_nonstring_and_topology_raise(monkeypatch, tmp_path):
    success = _CountedPathLike(str(package(tmp_path / "pathlike.xlsx", sheet_one=worksheet(envelope(container(6, 1))))))
    assert len(read_worksheet_x14_cf_envelope(success).worksheets) == 2
    assert success.calls == 1
    nonstring = _CountedPathLike(6)
    assert error(nonstring) == ("invalid-package-path", f"{__name__}._CountedPathLike", "path", "TypeError")
    assert nonstring.calls == 1
    sentinel = RuntimeError("topology")
    raising = _CountedPathLike(str(tmp_path / "missing.xlsx"))
    monkeypatch.setattr(reader, "read_workbook_topology", lambda path: (_ for _ in ()).throw(sentinel))
    with pytest.raises(RuntimeError) as captured:
        read_worksheet_x14_cf_envelope(raising)
    assert captured.value is sentinel
    assert raising.calls == 1


def test_canonical_member_alias_and_collision_remain_distinct(tmp_path):
    alias = package(tmp_path / "alias.xlsx", sheet_one_name="xl/worksheets/%66irst.xml")
    assert error(alias) == (
        "noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/%66irst.xml",
    )
    collision = package(
        tmp_path / "collision.xlsx", extra_members=(("xl/worksheets/%66irst.xml", worksheet()),),
    )
    with pytest.raises(OPCWorkbookTopologyError) as captured:
        read_worksheet_x14_cf_envelope(collision)
    assert captured.value.as_tuple() == (
        "duplicate-normalized-part", "xl/worksheets/first.xml", "name", "xl/worksheets/%66irst.xml",
    )


def test_pathlike_called_once_and_topology_identity(monkeypatch, tmp_path):
    sentinel = RuntimeError("topology")
    monkeypatch.setattr(reader, "read_workbook_topology", lambda path: (_ for _ in ()).throw(sentinel))
    with pytest.raises(RuntimeError) as captured:
        read_worksheet_x14_cf_envelope(tmp_path / "missing.xlsx")
    assert captured.value is sentinel
