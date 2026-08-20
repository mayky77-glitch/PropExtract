from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError, WorkbookX14CfEnvelope,
    X14CfContainerEnvelope, X14CfRuleEnvelope, read_worksheet_x14_cf_envelope,
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


def test_empty_worksheets_and_valid_dv_are_unowned(tmp_path):
    dv = '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations><xm:sqref>A1</xm:sqref></x14:dataValidations></ext></extLst>'
    result = read_worksheet_x14_cf_envelope(envelope_package(tmp_path / "empty.xlsx", first=dv))
    assert result.worksheets[0].containers == result.worksheets[1].containers == ()
