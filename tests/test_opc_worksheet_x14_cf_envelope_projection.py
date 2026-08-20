from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as owner_topology
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError, WorkbookX14CfEnvelope,
    WorksheetX14CfEnvelope, X14CfContainerEnvelope, X14CfContainerOwner,
    X14CfRuleEnvelope, read_worksheet_x14_cf_envelope,
    read_worksheet_x14_cf_owner_topology,
)
from tests.opc_worksheet_x14_cf_envelope_fixture_factory import cf, container, envelope_package, rule


PART = "xl/worksheets/first.xml"


def error(path):
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as caught:
        read_worksheet_x14_cf_envelope(path)
    return caught.value.as_tuple()


def test_two_sheet_projection_order_and_immutable_records(tmp_path):
    first = '<sheetData><row r="6"/><row r="10"/></sheetData>' + cf(
        container(rule(priority="20", formula="ROW()=6", dxf="<x14:dxf><font/></x14:dxf>"), "A6")
        + container(rule(priority="2", stop="false", formula="ROW()=10", dxf="<x14:dxf><font/><fill/></x14:dxf>"), "A10")
    )
    second = '<sheetData><row r="104"/></sheetData>' + cf(container(rule(priority="7", stop="true", formula="ROW()=104"), "B104"))
    package_path = envelope_package(tmp_path / "ok.xlsx", first=first, second=second)
    result = read_worksheet_x14_cf_envelope(package_path)
    topology = read_worksheet_x14_cf_owner_topology(package_path)
    assert isinstance(result, WorkbookX14CfEnvelope)
    assert asdict(result) == {
        "worksheets": ({
            "worksheet": {"name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one", "worksheet_part": {"value": PART}},
            "containers": ({
                "owner": {"owner_path": f"{PART}/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1},
                "sqref_text": "A6",
                "rules": ({"owner_path": f"{PART}/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]", "document_order": 1, "type": "expression", "priority": 20, "stop_if_true": None, "rule_id": "{01234567-89Ab-cDef-0123-456789aBcDeF}", "formula": "ROW()=6", "has_inline_dxf": True},),
            }, {
                "owner": {"owner_path": f"{PART}/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]", "document_order": 2},
                "sqref_text": "A10",
                "rules": ({"owner_path": f"{PART}/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]/cfRule[1]", "document_order": 2, "type": "expression", "priority": 2, "stop_if_true": False, "rule_id": "{01234567-89Ab-cDef-0123-456789aBcDeF}", "formula": "ROW()=10", "has_inline_dxf": True},),
            }),
        }, {
            "worksheet": {"name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two", "worksheet_part": {"value": "xl/worksheets/second.xml"}},
            "containers": ({
                "owner": {"owner_path": "xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1},
                "sqref_text": "B104",
                "rules": ({"owner_path": "xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]", "document_order": 1, "type": "expression", "priority": 7, "stop_if_true": True, "rule_id": "{01234567-89Ab-cDef-0123-456789aBcDeF}", "formula": "ROW()=104", "has_inline_dxf": True},),
            },),
        }),
    }
    assert result.worksheets[0].worksheet == topology.worksheets[0].worksheet
    assert result.worksheets[0].containers[0].owner == topology.worksheets[0].containers[0]
    assert isinstance(result.worksheets[0].containers[0].owner, X14CfContainerOwner)
    assert [rule.document_order for sheet in result.worksheets for box in sheet.containers for rule in box.rules] == [1, 2, 1]
    assert [rule.priority for box in result.worksheets[0].containers for rule in box.rules] == [20, 2]
    assert result.worksheets[0].containers[0].rules[0].owner_path.endswith("conditionalFormatting[1]/cfRule[1]")
    assert result.worksheets[0].containers[1].rules[0].stop_if_true is False
    assert result.worksheets[1].containers[0].rules[0].stop_if_true is True
    assert tuple(field.name for field in fields(X14CfRuleEnvelope)) == ("owner_path", "document_order", "type", "priority", "stop_if_true", "rule_id", "formula", "has_inline_dxf")
    assert tuple(field.name for field in fields(X14CfContainerEnvelope)) == ("owner", "sqref_text", "rules")
    assert tuple(field.name for field in fields(WorksheetX14CfEnvelope)) == ("worksheet", "containers")
    assert tuple(field.name for field in fields(WorkbookX14CfEnvelope)) == ("worksheets",)
    for value, attribute in ((result, "worksheets"), (result.worksheets[0], "containers"), (result.worksheets[0].containers[0], "sqref_text"), (result.worksheets[0].containers[0].owner, "owner_path"), (result.worksheets[0].containers[0].rules[0], "formula")):
        with pytest.raises(FrozenInstanceError):
            setattr(value, attribute, None)


def test_duplicate_priorities_are_worksheet_wide_and_x1_fault_precedes_x2(tmp_path):
    duplicate = container(rule(priority="4")) + container(rule(priority="4"), "B1")
    assert error(envelope_package(tmp_path / "duplicate.xlsx", first=cf(duplicate))) == ("duplicate-x14-cf-priority", PART, "priority", "4")
    malformed_owner = '<x14:cfRule/>' + cf(container(rule(priority="0")))
    assert error(envelope_package(tmp_path / "x1-first.xlsx", first=malformed_owner)) == (
        "invalid-x14-cf-parent", PART, "tag", "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}cfRule",
    )


def test_priority_uses_xml_whitespace_signed_lexical_and_numeric_identity(tmp_path):
    valid = container(rule(priority=" \t+0001\r\n"), "A1") + container(rule(priority="0002"), "B1")
    result = read_worksheet_x14_cf_envelope(envelope_package(tmp_path / "lexical.xlsx", first=cf(valid)))
    assert [item.priority for box in result.worksheets[0].containers for item in box.rules] == [1, 2]
    duplicate = container(rule(priority="1"), "A1") + container(rule(priority="+001"), "B1")
    assert error(envelope_package(tmp_path / "numeric-duplicate.xlsx", first=cf(duplicate))) == (
        "duplicate-x14-cf-priority", PART, "priority", "1",
    )
    for token in ("\u00a01\u00a0", "-1", "+", "0000", "9" * 129):
        assert error(envelope_package(tmp_path / f"priority-{len(token)}.xlsx", first=cf(container(rule(priority=token))))) == (
            "invalid-x14-cf-priority", PART, "priority", token,
        )


@pytest.mark.parametrize(("body", "expected"), [
    (container(rule(priority="0"), "A1").replace("</xm:sqref>", "</xm:sqref><xm:sqref>B1</xm:sqref>"), ("invalid-x14-cf-priority", PART, "priority", "0")),
    ('<x14:conditionalFormatting><xm:sqref>A1</xm:sqref>' + rule(priority="0") + '</x14:conditionalFormatting>', ("invalid-x14-cf-order", PART, "conditionalFormatting", "cfRule,sqref")),
    (container(rule(priority="1"), "A1").replace("</xm:sqref>", "</xm:sqref><xm:sqref>B1</xm:sqref>"), ("invalid-x14-cf-order", PART, "conditionalFormatting", "cfRule,sqref")),
    (container(rule(priority="1"), "A1") + container(rule(priority="1"), "B1").replace("</xm:sqref>", "</xm:sqref><xm:sqref>C1</xm:sqref>"), ("duplicate-x14-cf-priority", PART, "priority", "1")),
])
def test_container_child_state_machine_preserves_document_order(tmp_path, body, expected):
    assert error(envelope_package(tmp_path / "ordered-fault.xlsx", first=cf(body))) == expected


@pytest.mark.parametrize(("body", "expected"), [
    (container(rule().replace(' type="expression"', '')), ("invalid-x14-cf-cardinality", PART, "attribute", "type")),
    (container(rule().replace(' id=', ' unexpected="x" id=')), ("unknown-x14-cf-attribute", PART, "attribute", "unexpected")),
    (container(rule(priority="-1")), ("invalid-x14-cf-priority", PART, "priority", "-1")),
    (container(rule(priority="0000")), ("invalid-x14-cf-priority", PART, "priority", "0000")),
    (container(rule(stop="False")), ("invalid-x14-cf-boolean", PART, "stopIfTrue", "False")),
    (container(rule(rule_id="{01234567-89ab-cdef-0123-456789abcdeZ}")), ("invalid-x14-cf-id", PART, "id", "{01234567-89ab-cdef-0123-456789abcdeZ}")),
    (container(rule().replace('<xm:f>A1>0</xm:f>', '<xm:f><nested/></xm:f>')), ("invalid-x14-cf-formula", PART, "f", "content")),
    (container(rule().replace('<xm:f>A1>0</xm:f>', '<xm:f/>')), ("invalid-x14-cf-formula", PART, "f", "content")),
    (container(rule().replace('<xm:f>A1>0</xm:f>', '')), ("invalid-x14-cf-cardinality", PART, "cfRule", "f,dxf")),
    (container(rule().replace('</xm:f>', '</xm:f>x')), ("invalid-x14-cf-content", PART, "cfRule", "tail")),
    (container(rule().replace('</xm:f>', '</xm:f><xm:f>A2>0</xm:f>')), ("invalid-x14-cf-cardinality", PART, "cfRule", "f,dxf")),
    (container(rule().replace('<x14:dxf><font/></x14:dxf>', '')), ("invalid-x14-cf-cardinality", PART, "cfRule", "f,dxf")),
    (container(rule().replace('<x14:dxf><font/></x14:dxf>', '<x14:dxf>text<font/></x14:dxf>')), ("invalid-x14-cf-dxf", PART, "dxf", "content")),
    (container(rule().replace('<x14:dxf><font/></x14:dxf>', '<x14:dxf extra="x"><font/></x14:dxf>')), ("invalid-x14-cf-dxf", PART, "dxf", "content")),
    (container(rule().replace('<font/>', '<foreign/>')), ("unknown-x14-cf-child", PART, "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}foreign")),
    (container(rule().replace('<font/>', '<x14:foreign/>')), ("unknown-x14-cf-child", PART, "tag", "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}foreign")),
    (container(rule().replace('<font/>', '<xm:foreign/>')), ("unknown-x14-cf-child", PART, "tag", "{http://schemas.microsoft.com/office/excel/2006/main}foreign")),
    (container(rule().replace('<font/>', '<font/><font/>')), ("invalid-x14-cf-dxf", PART, "child", "font,fill")),
    (container(rule().replace('<font/>', '<fill/><font/>')), ("invalid-x14-cf-dxf", PART, "child", "font,fill")),
    (container(rule().replace('<font/>', '<font/>x')), ("invalid-x14-cf-dxf", PART, "dxf", "tail")),
    (container(rule(), " "), ("invalid-x14-cf-sqref", PART, "sqref", "content")),
    (container(rule()).replace('<xm:sqref>A1</xm:sqref>', '<xm:sqref extra="x">A1</xm:sqref>'), ("invalid-x14-cf-sqref", PART, "sqref", "content")),
    (container(rule()).replace('<xm:sqref>A1</xm:sqref>', '<xm:sqref><nested/></xm:sqref>'), ("invalid-x14-cf-sqref", PART, "sqref", "content")),
    (container(rule()).replace('</xm:sqref>', '</xm:sqref>x'), ("invalid-x14-cf-content", PART, "conditionalFormatting", "tail")),
    (container(rule()).replace('<xm:sqref>A1</xm:sqref>', ''), ("invalid-x14-cf-order", PART, "conditionalFormatting", "cfRule,sqref")),
    ('<x14:conditionalFormatting><xm:sqref>A1</xm:sqref></x14:conditionalFormatting>', ("invalid-x14-cf-cardinality", PART, "conditionalFormatting", "cfRule")),
    ('<x14:conditionalFormatting><xm:sqref>A1</xm:sqref>' + rule() + '</x14:conditionalFormatting>', ("invalid-x14-cf-order", PART, "conditionalFormatting", "cfRule,sqref")),
])
def test_semantic_negative_matrix_returns_one_exact_tuple(tmp_path, body, expected):
    assert error(envelope_package(tmp_path / "exact.xlsx", first=cf(body))) == expected


def test_empty_worksheets_and_valid_dv_are_unowned(tmp_path):
    dv = '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations><xm:sqref>A1</xm:sqref></x14:dataValidations></ext></extLst>'
    result = read_worksheet_x14_cf_envelope(envelope_package(tmp_path / "empty.xlsx", first=dv))
    assert result.worksheets[0].containers == result.worksheets[1].containers == ()


def test_envelope_uses_one_accepted_pipeline_and_publishes_only_after_two_sheets_validate(tmp_path, monkeypatch):
    calls = {"accepted": 0, "topology": 0, "member": 0, "xml": 0}
    package_path = envelope_package(
        tmp_path / "pipeline.xlsx",
        first=cf(container(rule(priority="1"), "A1")),
        second=cf(container(rule(priority="2"), "B1")),
    )
    original_accepted = owner_topology._accepted
    original_topology = owner_topology.read_workbook_topology
    original_member = owner_topology._member
    original_xml = owner_topology._xml

    def accepted(path):
        calls["accepted"] += 1
        return original_accepted(path)

    def topology(path):
        calls["topology"] += 1
        return original_topology(path)

    def member(path, part):
        calls["member"] += 1
        return original_member(path, part)

    def xml(payload, part):
        calls["xml"] += 1
        return original_xml(payload, part)

    monkeypatch.setattr(owner_topology, "_accepted", accepted)
    monkeypatch.setattr(owner_topology, "read_workbook_topology", topology)
    monkeypatch.setattr(owner_topology, "_member", member)
    monkeypatch.setattr(owner_topology, "_xml", xml)
    result = read_worksheet_x14_cf_envelope(package_path)
    assert calls == {"accepted": 1, "topology": 1, "member": 2, "xml": 2}
    assert len(result.worksheets) == 2

    invalid = envelope_package(
        tmp_path / "atomic.xlsx",
        first=cf(container(rule(priority="1"), "A1")),
        second=cf(container(rule(priority="0"), "B1")),
    )
    assert error(invalid) == ("invalid-x14-cf-priority", "xl/worksheets/second.xml", "priority", "0")
