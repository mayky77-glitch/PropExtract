"""Acceptance tests for direct X14 CF expression-rule envelope projection."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as reader
from rns_import_server.opc_part_uri import CanonicalPartURI
from rns_import_server.opc_workbook_topology import WorkbookTopology, WorksheetDescriptor
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError, WorkbookX14CfRuleEnvelope,
    X14CfOwnerRuleEnvelope, X14CfRuleEnvelope, WorksheetX14CfRuleEnvelope,
    read_worksheet_x14_cf_owner_topology, read_worksheet_x14_cf_rule_envelope,
)
from tests.opc_worksheet_x14_cf_rule_envelope_fixture_factory import corpus, extension, owner, rule


PART = "xl/worksheets/first.xml"


def error(path):
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_rule_envelope(path)
    return captured.value.as_tuple()


def test_two_sheet_projection_field_order_and_immutability(tmp_path):
    first = ('<sheetData><row r="6"/><row r="10"/></sheetData>' + extension(
        owner(rule(priority=" +0007 ", stop="true", formula="A6&gt;0"), rule(priority="2", stop="0", formula="A6&lt;9"), sqref='<xm:sqref broken="x">bad</xm:sqref>') +
        owner(rule(priority="1", formula="B10=1"), sqref="<xm:sqref/><xm:sqref>duplicated</xm:sqref>")))
    second = '<sheetData><row r="104"/></sheetData>' + extension(owner(rule(priority="2147483647", stop="false", formula="C104&gt;0")))
    result = read_worksheet_x14_cf_rule_envelope(corpus(tmp_path / "projection.xlsx", first=first, second=second))
    assert isinstance(result, WorkbookX14CfRuleEnvelope)
    assert tuple(field.name for field in fields(X14CfRuleEnvelope)) == (
        "owner_path", "document_order", "type", "priority", "stop_if_true", "rule_id", "formula", "has_inline_dxf")
    assert tuple(field.name for field in fields(X14CfOwnerRuleEnvelope)) == ("owner", "rules")
    assert tuple(field.name for field in fields(WorksheetX14CfRuleEnvelope)) == ("worksheet", "containers")
    assert result.worksheets[0].containers[0].rules[0] == X14CfRuleEnvelope(
        PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]",
        1, "expression", 7, True, "{00112233-4455-6677-8899-AABBCCDDEEFF}", "A6>0", True)
    assert [item.document_order for group in result.worksheets[0].containers for item in group.rules] == [1, 2, 3]
    assert result.worksheets[1].containers[0].rules[0].document_order == 1
    assert result.worksheets[0].containers[1].rules[0].owner_path.endswith("conditionalFormatting[2]/cfRule[1]")
    assert asdict(result) == {
        "worksheets": (
            {"worksheet": {"name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one", "worksheet_part": {"value": PART}}, "containers": (
                {"owner": {"owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1}, "rules": (
                    {"owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]", "document_order": 1, "type": "expression", "priority": 7, "stop_if_true": True, "rule_id": "{00112233-4455-6677-8899-AABBCCDDEEFF}", "formula": "A6>0", "has_inline_dxf": True},
                    {"owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[2]", "document_order": 2, "type": "expression", "priority": 2, "stop_if_true": False, "rule_id": "{00112233-4455-6677-8899-AABBCCDDEEFF}", "formula": "A6<9", "has_inline_dxf": True},)},
                {"owner": {"owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]", "document_order": 2}, "rules": (
                    {"owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]/cfRule[1]", "document_order": 3, "type": "expression", "priority": 1, "stop_if_true": None, "rule_id": "{00112233-4455-6677-8899-AABBCCDDEEFF}", "formula": "B10=1", "has_inline_dxf": True},)} )},
            {"worksheet": {"name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two", "worksheet_part": {"value": "xl/worksheets/second.xml"}}, "containers": (
                {"owner": {"owner_path": "xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1}, "rules": (
                    {"owner_path": "xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]", "document_order": 1, "type": "expression", "priority": 2147483647, "stop_if_true": False, "rule_id": "{00112233-4455-6677-8899-AABBCCDDEEFF}", "formula": "C104>0", "has_inline_dxf": True},)}, )},
        ),
    }
    for instance, attr in ((result, "worksheets"), (result.worksheets[0], "containers"),
                           (result.worksheets[0].containers[0], "rules"),
                           (result.worksheets[0].containers[0].rules[0], "priority")):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, attr, None)


@pytest.mark.parametrize(("body", "expected"), [
    (owner(rule(extra=' z="1" a="1"')), ("unknown-x14-cf-attribute", "attribute", "a")),
    ('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1"><xm:f>A1</xm:f><x14:dxf/></x14:cfRule></x14:conditionalFormatting>', ("invalid-x14-cf-cardinality", "attribute", "id")),
    (owner(rule(priority="0")), ("invalid-x14-cf-priority", "priority", "0")),
    (owner(rule(priority="\u00a01")), ("invalid-x14-cf-priority", "priority", "\u00a01")),
    (owner(rule(priority="99999999999")), ("invalid-x14-cf-priority", "priority", "99999999999")),
    (owner(rule(stop="yes")), ("invalid-x14-cf-boolean", "stopIfTrue", "yes")),
    (owner(rule(rule_id="not-a-guid")), ("invalid-x14-cf-id", "id", "not-a-guid")),
    (owner(rule(formula="   ")), ("invalid-x14-cf-formula", "f", "text")),
    (owner(rule(children='<x14:dxf/><xm:f>A1</xm:f>')), ("invalid-x14-cf-order", "cfRule", "f,dxf")),
    (owner(rule(children='<xm:f>A1</xm:f>')), ("invalid-x14-cf-cardinality", "cfRule", "dxf")),
    (owner(rule(children='<xm:f>A1</xm:f><x14:dxf bad="1"/>')), ("invalid-x14-cf-dxf", "dxf", "attribute")),
])
def test_rule_semantic_error_tuples(tmp_path, body, expected):
    assert error(corpus(tmp_path / "bad.xlsx", first=extension(body))) == (expected[0], PART, expected[1], expected[2])


@pytest.mark.parametrize(("priority", "expected"), [
    ("-1", "-1"), ("+0", "+0"), ("1.0", "1.0"), ("1 2", "1 2"),
    ("2147483648", "2147483648"), ("10000000000", "10000000000"),
])
def test_priority_lexical_and_bounds_failures(tmp_path, priority, expected):
    assert error(corpus(tmp_path / "priority.xlsx", first=extension(owner(rule(priority=priority))))) == (
        "invalid-x14-cf-priority", PART, "priority", expected)


@pytest.mark.parametrize("priority", ("\u00a01", "\u00851", "\u20031", "1\u00a0", "1\u0085", "1\u2003"))
def test_only_xml_whitespace_is_collapsed(tmp_path, priority):
    assert error(corpus(tmp_path / "non-xml-space.xlsx", first=extension(owner(rule(priority=priority))))) == (
        "invalid-x14-cf-priority", PART, "priority", priority)


def test_xml_whitespace_and_arbitrarily_many_leading_zeroes_are_valid(tmp_path):
    priority = " \t\r\n+" + "0" * 5000 + "1\r\n "
    result = read_worksheet_x14_cf_rule_envelope(corpus(
        tmp_path / "xml-space.xlsx", first=extension(owner(rule(priority=priority)))))
    assert result.worksheets[0].containers[0].rules[0].priority == 1


@pytest.mark.parametrize("kind", ("cellIs", "containsText", "colorScale", "dataBar", "iconSet", ""))
def test_non_expression_rule_types_are_rejected(tmp_path, kind):
    body = owner(rule().replace('type="expression"', f'type="{kind}"'))
    assert error(corpus(tmp_path / "type.xlsx", first=extension(body))) == (
        "unsupported-x14-cf-rule-type", PART, "type", kind)


@pytest.mark.parametrize(("children", "expected"), [
    ('<xm:f>A1</xm:f><xm:f>B1</xm:f><x14:dxf/>', ("invalid-x14-cf-cardinality", "cfRule", "f")),
    ('<xm:f>A1</xm:f><x14:dxf/><x14:dxf/>', ("invalid-x14-cf-cardinality", "cfRule", "dxf")),
    ('<x14:dxf/><xm:f>A1</xm:f>', ("invalid-x14-cf-order", "cfRule", "f,dxf")),
    ('<xm:f attr="x">A1</xm:f><x14:dxf/>', ("invalid-x14-cf-formula", "f", "attribute")),
])
def test_f_and_dxf_cardinality_order_and_attributes(tmp_path, children, expected):
    assert error(corpus(tmp_path / "children.xlsx", first=extension(owner(rule(children=children))))) == (
        expected[0], PART, expected[1], expected[2])


@pytest.mark.parametrize(("children", "expected"), [
    ('<x14:dxf/><xm:f>A1</xm:f><xm:f>B1</xm:f>', ("invalid-x14-cf-order", "cfRule", "f,dxf")),
    ('<xm:f bad="x">A1</xm:f><xm:f>B1</xm:f><x14:dxf/>', ("invalid-x14-cf-formula", "f", "attribute")),
    ('<xm:f>A1</xm:f><x14:dxf bad="x"/><x14:dxf/>', ("invalid-x14-cf-dxf", "dxf", "attribute")),
])
def test_child_event_precedence_is_immediate(tmp_path, children, expected):
    assert error(corpus(tmp_path / "event-order.xlsx", first=extension(owner(rule(children=children))))) == (
        expected[0], PART, expected[1], expected[2])


def test_inline_dxf_descendants_are_opaque(tmp_path):
    children = '<xm:f>A1</xm:f><x14:dxf><x14:font><x14:color rgb="FF00FF00"/></x14:font><x14:fill><x14:patternFill/></x14:fill></x14:dxf>'
    result = read_worksheet_x14_cf_rule_envelope(corpus(
        tmp_path / "opaque-dxf.xlsx", first=extension(owner(rule(children=children)))))
    assert result.worksheets[0].containers[0].rules[0].has_inline_dxf is True


@pytest.mark.parametrize(("children", "expected"), [
    ('<xm:f><foreign/></xm:f><x14:dxf/>', ("invalid-x14-cf-formula", "f", "child")),
    ('<xm:f>A1</xm:f><x14:dxf>text</x14:dxf>', ("invalid-x14-cf-dxf", "dxf", "text")),
    ('<xm:f>A1</xm:f><x14:dxf/><foreign/>', ("unknown-x14-cf-child", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}foreign")),
])
def test_nested_text_and_foreign_children_are_exact(tmp_path, children, expected):
    assert error(corpus(tmp_path / "nested.xlsx", first=extension(owner(rule(children=children))))) == (
        expected[0], PART, expected[1], expected[2])


@pytest.mark.parametrize("sqref", (
    "", "<xm:sqref/>", "<xm:sqref bad=\"x\"> malformed </xm:sqref>",
    "<xm:sqref>A1</xm:sqref><xm:sqref>B2</xm:sqref>",
))
def test_sqref_is_not_projected_or_validated(tmp_path, sqref):
    body = extension(owner(rule(priority="4"), sqref=sqref))
    result = read_worksheet_x14_cf_rule_envelope(corpus(tmp_path / "sqref.xlsx", first=body))
    assert result.worksheets[0].containers[0].rules[0].priority == 4


def test_priority_is_worksheet_global_and_atomic(tmp_path):
    first = extension(owner(rule(priority="01")) + owner(rule(priority="+1")))
    assert error(corpus(tmp_path / "duplicate.xlsx", first=first)) == (
        "duplicate-x14-cf-priority", PART, "priority", "1")
    first = extension(owner(rule(priority="1")))
    second = extension(owner(rule(priority="1")))
    assert isinstance(read_worksheet_x14_cf_rule_envelope(corpus(tmp_path / "per-sheet.xlsx", first=first, second=second)), WorkbookX14CfRuleEnvelope)


class _CountedPath:
    def __init__(self, value): self.value=value; self.calls=0
    def __fspath__(self): self.calls+=1; return self.value


def test_new_api_path_topology_identity_and_one_xml_parse_per_sheet(monkeypatch, tmp_path):
    path = corpus(tmp_path / "io.xlsx", first=extension(owner(rule())), second=extension(owner(rule(priority="2"))))
    counted = _CountedPath(str(path))
    original = reader.ET.fromstring; calls=[]
    def parse(payload): calls.append(payload); return original(payload)
    monkeypatch.setattr(reader.ET, "fromstring", parse)
    result = read_worksheet_x14_cf_rule_envelope(counted)
    assert counted.calls == 1 and sum(payload.startswith(b"<worksheet") for payload in calls) == 2
    topology = read_worksheet_x14_cf_owner_topology(path)
    assert tuple(group.owner for group in result.worksheets[0].containers) == topology.worksheets[0].containers
    sentinel = RuntimeError("topology")
    monkeypatch.setattr(reader, "read_workbook_topology", lambda value: (_ for _ in ()).throw(sentinel))
    with pytest.raises(RuntimeError) as captured:
        read_worksheet_x14_cf_rule_envelope(str(path))
    assert captured.value is sentinel


def test_second_worksheet_failure_is_atomic(tmp_path):
    valid = extension(owner(rule()))
    invalid = extension(owner(rule(priority="0")))
    assert error(corpus(tmp_path / "atomic.xlsx", first=valid, second=invalid)) == (
        "invalid-x14-cf-priority", "xl/worksheets/second.xml", "priority", "0")
