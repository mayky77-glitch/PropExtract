from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError, WorkbookX14CfEnvelope,
    WorksheetX14CfEnvelope, X14CfContainerEnvelope, X14CfRuleEnvelope,
    read_worksheet_x14_cf_envelope,
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
    result = read_worksheet_x14_cf_envelope(envelope_package(tmp_path / "ok.xlsx", first=first, second=second))
    assert isinstance(result, WorkbookX14CfEnvelope)
    assert asdict(result)["worksheets"][0]["containers"][0]["sqref_text"] == "A6"
    assert [rule.document_order for sheet in result.worksheets for box in sheet.containers for rule in box.rules] == [1, 2, 1]
    assert [rule.priority for box in result.worksheets[0].containers for rule in box.rules] == [20, 2]
    assert result.worksheets[0].containers[0].rules[0].owner_path.endswith("conditionalFormatting[1]/cfRule[1]")
    assert result.worksheets[0].containers[1].rules[0].stop_if_true is False
    assert result.worksheets[1].containers[0].rules[0].stop_if_true is True
    assert tuple(field.name for field in fields(X14CfRuleEnvelope)) == ("owner_path", "document_order", "type", "priority", "stop_if_true", "rule_id", "formula", "has_inline_dxf")
    assert tuple(field.name for field in fields(X14CfContainerEnvelope)) == ("owner", "sqref_text", "rules")
    assert tuple(field.name for field in fields(WorksheetX14CfEnvelope)) == ("worksheet", "containers")
    assert tuple(field.name for field in fields(WorkbookX14CfEnvelope)) == ("worksheets",)
    for value, attribute in ((result, "worksheets"), (result.worksheets[0], "containers"), (result.worksheets[0].containers[0], "sqref_text"), (result.worksheets[0].containers[0].rules[0], "formula")):
        with pytest.raises(FrozenInstanceError):
            setattr(value, attribute, None)


@pytest.mark.parametrize(("body", "code"), [
    (container(rule(priority="0")), "invalid-x14-cf-priority"),
    (container(rule(priority="2147483648")), "invalid-x14-cf-priority"),
    (container(rule(stop="TRUE")), "invalid-x14-cf-boolean"),
    (container(rule(rule_id="bad")), "invalid-x14-cf-id"),
    (container(rule().replace('type="expression"', 'type="colorScale"')), "unsupported-x14-cf-rule-type"),
    (container(rule().replace(' id=', ' odd="x" id=')), "unknown-x14-cf-attribute"),
    (container(rule().replace('<xm:f>', '<xm:f extra="x">')), "invalid-x14-cf-formula"),
    (container(rule().replace('<xm:f>A1>0</xm:f>', '<xm:f/>')), "invalid-x14-cf-formula"),
    (container(rule().replace('<font/>', '<fill/><font/>')), "invalid-x14-cf-dxf"),
    (container(rule()) .replace('<xm:sqref>A1</xm:sqref>', '<xm:sqref/>'), "invalid-x14-cf-sqref"),
    (container(rule()).replace('</xm:sqref>', '</xm:sqref><xm:sqref>A2</xm:sqref>'), "invalid-x14-cf-order"),
])
def test_semantic_fault_matrix(tmp_path, body, code):
    assert error(envelope_package(tmp_path / f"{code}.xlsx", first=cf(body))) [0] == code


def test_duplicate_priorities_are_worksheet_wide_and_x1_fault_precedes_x2(tmp_path):
    duplicate = container(rule(priority="4")) + container(rule(priority="4"), "B1")
    assert error(envelope_package(tmp_path / "duplicate.xlsx", first=cf(duplicate))) == ("duplicate-x14-cf-priority", PART, "priority", "4")
    malformed_owner = '<x14:cfRule/>' + cf(container(rule(priority="0")))
    assert error(envelope_package(tmp_path / "x1-first.xlsx", first=malformed_owner))[0] == "invalid-x14-cf-parent"


def test_priority_uses_xml_whitespace_signed_lexical_and_numeric_identity(tmp_path):
    valid = container(rule(priority=" \t+0001\r\n"), "A1") + container(rule(priority="0002"), "B1")
    result = read_worksheet_x14_cf_envelope(envelope_package(tmp_path / "lexical.xlsx", first=cf(valid)))
    assert [item.priority for box in result.worksheets[0].containers for item in box.rules] == [1, 2]
    duplicate = container(rule(priority="1"), "A1") + container(rule(priority="+001"), "B1")
    assert error(envelope_package(tmp_path / "numeric-duplicate.xlsx", first=cf(duplicate))) == (
        "duplicate-x14-cf-priority", PART, "priority", "1",
    )
    for token in ("\u00a01\u00a0", "-1", "+", "0000", "9" * 129):
        assert error(envelope_package(tmp_path / f"priority-{len(token)}.xlsx", first=cf(container(rule(priority=token)))))[0] == "invalid-x14-cf-priority"


def test_earlier_rule_semantics_precede_later_container_structure_faults(tmp_path):
    combined = container(rule(priority="0"), "A1").replace(
        "</xm:sqref>", "</xm:sqref><xm:sqref>B1</xm:sqref>",
    )
    assert error(envelope_package(tmp_path / "ordered-fault.xlsx", first=cf(combined))) == (
        "invalid-x14-cf-priority", PART, "priority", "0",
    )


@pytest.mark.parametrize(("body", "expected"), [
    (container(rule().replace(' type="expression"', '')), ("invalid-x14-cf-cardinality", PART, "attribute", "type")),
    (container(rule().replace(' id=', ' unexpected="x" id=')), ("unknown-x14-cf-attribute", PART, "attribute", "unexpected")),
    (container(rule(priority="-1")), ("invalid-x14-cf-priority", PART, "priority", "-1")),
    (container(rule(priority="0000")), ("invalid-x14-cf-priority", PART, "priority", "0000")),
    (container(rule(stop="False")), ("invalid-x14-cf-boolean", PART, "stopIfTrue", "False")),
    (container(rule(rule_id="{01234567-89ab-cdef-0123-456789abcdeZ}")), ("invalid-x14-cf-id", PART, "id", "{01234567-89ab-cdef-0123-456789abcdeZ}")),
    (container(rule().replace('<xm:f>A1>0</xm:f>', '<xm:f><nested/></xm:f>')), ("invalid-x14-cf-formula", PART, "f", "content")),
    (container(rule().replace('<xm:f>A1>0</xm:f>', '<xm:f/>')), ("invalid-x14-cf-formula", PART, "f", "content")),
    (container(rule().replace('<x14:dxf><font/></x14:dxf>', '')), ("invalid-x14-cf-cardinality", PART, "cfRule", "f,dxf")),
    (container(rule().replace('<x14:dxf><font/></x14:dxf>', '<x14:dxf extra="x"><font/></x14:dxf>')), ("invalid-x14-cf-dxf", PART, "dxf", "content")),
    (container(rule().replace('<font/>', '<foreign/>')), ("unknown-x14-cf-child", PART, "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}foreign")),
    (container(rule().replace('<font/>', '<font/>x')), ("invalid-x14-cf-dxf", PART, "dxf", "tail")),
    (container(rule(), " "), ("invalid-x14-cf-sqref", PART, "sqref", "content")),
    (container(rule()).replace('<xm:sqref>A1</xm:sqref>', '<xm:sqref><nested/></xm:sqref>'), ("invalid-x14-cf-sqref", PART, "sqref", "content")),
    ('<x14:conditionalFormatting><xm:sqref>A1</xm:sqref></x14:conditionalFormatting>', ("invalid-x14-cf-cardinality", PART, "conditionalFormatting", "cfRule")),
    ('<x14:conditionalFormatting><xm:sqref>A1</xm:sqref>' + rule() + '</x14:conditionalFormatting>', ("invalid-x14-cf-order", PART, "conditionalFormatting", "cfRule,sqref")),
])
def test_semantic_negative_matrix_returns_one_exact_tuple(tmp_path, body, expected):
    assert error(envelope_package(tmp_path / "exact.xlsx", first=cf(body))) == expected


def test_empty_worksheets_and_valid_dv_are_unowned(tmp_path):
    dv = '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations><xm:sqref>A1</xm:sqref></x14:dataValidations></ext></extLst>'
    result = read_worksheet_x14_cf_envelope(envelope_package(tmp_path / "empty.xlsx", first=dv))
    assert result.worksheets[0].containers == result.worksheets[1].containers == ()
