"""Frozen X2a corpus for X14 conditional-formatting rule envelopes."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as reader
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError,
    WorkbookX14CfOwnerTopology,
    WorkbookX14CfRuleEnvelope,
    WorksheetX14CfOwnerTopology,
    WorksheetX14CfRuleEnvelope,
    X14CfContainerOwner,
    X14CfOwnerRuleEnvelope,
    X14CfRuleEnvelope,
    read_worksheet_x14_cf_owner_topology,
    read_worksheet_x14_cf_rule_envelope,
)
from tests.opc_worksheet_x14_cf_owner_fixture_factory import X14, XM
from tests.opc_worksheet_x14_cf_rule_envelope_fixture_factory import corpus, extension, owner, rule


PART = "xl/worksheets/first.xml"
SECOND_PART = "xl/worksheets/second.xml"
GUID = "{00112233-4455-6677-8899-AABBCCDDEEFF}"


def error(path):
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_rule_envelope(path)
    return captured.value.as_tuple()


def test_complete_two_sheet_projection_public_field_order_and_immutability(tmp_path):
    first = (
        '<sheetData><row r="6"/><row r="10"/></sheetData>'
        + extension(
            owner(
                rule(priority="7", stop="1", formula="A6&gt;0", children=(
                    '<xm:f>A6&gt;0</xm:f><x14:dxf><x14:font><x14:color rgb="FF00FF00"/>'
                    '</x14:font></x14:dxf>'
                )),
                rule(priority="2", stop="false", formula="A6&lt;9", children=(
                    '<xm:f>A6&lt;9</xm:f><x14:dxf><x14:font/><x14:fill><x14:patternFill/>'
                    '</x14:fill></x14:dxf>'
                )),
            )
            + owner(rule(priority="1", formula="B10=1"))
        )
    )
    second = (
        '<sheetData><row r="104"/></sheetData>'
        + extension(owner(rule(priority="3", stop="true", formula="C104&gt;0")))
    )
    path = corpus(tmp_path / "projection.xlsx", first=first, second=second)
    result = read_worksheet_x14_cf_rule_envelope(path)
    topology = read_worksheet_x14_cf_owner_topology(path)

    assert isinstance(result, WorkbookX14CfRuleEnvelope)
    assert tuple(field.name for field in fields(X14CfContainerOwner)) == ("owner_path", "document_order")
    assert tuple(field.name for field in fields(WorksheetX14CfOwnerTopology)) == ("worksheet", "containers")
    assert tuple(field.name for field in fields(WorkbookX14CfOwnerTopology)) == ("worksheets",)
    assert tuple(field.name for field in fields(X14CfRuleEnvelope)) == (
        "owner_path", "document_order", "type", "priority", "stop_if_true", "rule_id", "formula",
        "has_inline_dxf",
    )
    assert tuple(field.name for field in fields(X14CfOwnerRuleEnvelope)) == ("owner", "rules")
    assert tuple(field.name for field in fields(WorksheetX14CfRuleEnvelope)) == ("worksheet", "containers")
    assert tuple(field.name for field in fields(WorkbookX14CfRuleEnvelope)) == ("worksheets",)
    assert tuple(group.owner for group in result.worksheets[0].containers) == topology.worksheets[0].containers
    assert tuple(group.owner for group in result.worksheets[1].containers) == topology.worksheets[1].containers
    assert tuple(sheet.worksheet for sheet in result.worksheets) == tuple(sheet.worksheet for sheet in topology.worksheets)
    assert [rule.document_order for group in result.worksheets[0].containers for rule in group.rules] == [1, 2, 3]
    assert [rule.document_order for group in result.worksheets[1].containers for rule in group.rules] == [1]
    assert [rule.owner_path for group in result.worksheets[0].containers for rule in group.rules] == [
        PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]",
        PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[2]",
        PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]/cfRule[1]",
    ]
    assert asdict(result) == {
        "worksheets": (
            {
                "worksheet": {
                    "name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one",
                    "worksheet_part": {"value": PART},
                },
                "containers": (
                    {
                        "owner": {
                            "owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]",
                            "document_order": 1,
                        },
                        "rules": (
                            {
                                "owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]",
                                "document_order": 1, "type": "expression", "priority": 7, "stop_if_true": True,
                                "rule_id": GUID, "formula": "A6>0", "has_inline_dxf": True,
                            },
                            {
                                "owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[2]",
                                "document_order": 2, "type": "expression", "priority": 2, "stop_if_true": False,
                                "rule_id": GUID, "formula": "A6<9", "has_inline_dxf": True,
                            },
                        ),
                    },
                    {
                        "owner": {
                            "owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]",
                            "document_order": 2,
                        },
                        "rules": (
                            {
                                "owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]/cfRule[1]",
                                "document_order": 3, "type": "expression", "priority": 1, "stop_if_true": None,
                                "rule_id": GUID, "formula": "B10=1", "has_inline_dxf": True,
                            },
                        ),
                    },
                ),
            },
            {
                "worksheet": {
                    "name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two",
                    "worksheet_part": {"value": SECOND_PART},
                },
                "containers": (
                    {
                        "owner": {
                            "owner_path": SECOND_PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]",
                            "document_order": 1,
                        },
                        "rules": (
                            {
                                "owner_path": SECOND_PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]",
                                "document_order": 1, "type": "expression", "priority": 3, "stop_if_true": True,
                                "rule_id": GUID, "formula": "C104>0", "has_inline_dxf": True,
                            },
                        ),
                    },
                ),
            },
        ),
    }
    for instance, attribute in (
        (result, "worksheets"),
        (result.worksheets[0], "containers"),
        (result.worksheets[0].containers[0], "rules"),
        (result.worksheets[0].containers[0].rules[0], "priority"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, attribute, None)


@pytest.mark.parametrize(("attrs", "expected"), [
    ('priority="1" id="' + GUID + '"', ("invalid-x14-cf-cardinality", "attribute", "type")),
    ('type="expression" id="' + GUID + '"', ("invalid-x14-cf-cardinality", "attribute", "priority")),
    ('type="expression" priority="1"', ("invalid-x14-cf-cardinality", "attribute", "id")),
    ('type="expression"', ("invalid-x14-cf-cardinality", "attribute", "id")),
    ("", ("invalid-x14-cf-cardinality", "attribute", "id")),
    ('type="expression" priority="1" id="' + GUID + '" z="1" a="1"', ("unknown-x14-cf-attribute", "attribute", "a")),
])
def test_required_attribute_cardinality_and_sorted_attribute_precedence(tmp_path, attrs, expected):
    body = '<x14:conditionalFormatting><x14:cfRule ' + attrs + '><xm:f>A1</xm:f><x14:dxf/></x14:cfRule></x14:conditionalFormatting>'
    assert error(corpus(tmp_path / "attributes.xlsx", first=extension(body))) == (expected[0], PART, expected[1], expected[2])


@pytest.mark.parametrize(("children", "expected"), [
    ("", ("invalid-x14-cf-cardinality", "cfRule", "f")),
    ("<xm:f/><x14:dxf/>", ("invalid-x14-cf-formula", "f", "text")),
    ("<xm:f>   </xm:f><x14:dxf/>", ("invalid-x14-cf-formula", "f", "text")),
    ("<xm:f>A1</xm:f>", ("invalid-x14-cf-cardinality", "cfRule", "dxf")),
    ("<xm:f>A1</xm:f><xm:f>B1</xm:f><x14:dxf/>", ("invalid-x14-cf-cardinality", "cfRule", "f")),
    ("<xm:f>A1</xm:f><x14:dxf/><x14:dxf/>", ("invalid-x14-cf-cardinality", "cfRule", "dxf")),
    ("<x14:dxf/><xm:f>A1</xm:f>", ("invalid-x14-cf-order", "cfRule", "f,dxf")),
    ("<xm:f bad=\"x\">A1</xm:f><x14:dxf/>", ("invalid-x14-cf-formula", "f", "attribute")),
    ("<xm:f>A1</xm:f><x14:dxf bad=\"x\"/>", ("invalid-x14-cf-dxf", "dxf", "attribute")),
    ("<xm:f><foreign/></xm:f><x14:dxf/>", ("invalid-x14-cf-formula", "f", "child")),
    ("<xm:f>A1</xm:f>tail<x14:dxf/>", ("invalid-x14-cf-content", "cfRule", "tail")),
    ("<xm:f>A1</xm:f><x14:dxf>text</x14:dxf>", ("invalid-x14-cf-dxf", "dxf", "text")),
    ("<xm:f>A1</xm:f><x14:dxf/>tail", ("invalid-x14-cf-content", "cfRule", "tail")),
])
def test_formula_and_dxf_semantic_negative_matrix(tmp_path, children, expected):
    assert error(corpus(tmp_path / "formula-dxf.xlsx", first=extension(owner(rule(children=children))))) == (
        expected[0], PART, expected[1], expected[2]
    )


@pytest.mark.parametrize(("children", "expected"), [
    ("<xm:f bad=\"x\">A1</xm:f><x14:dxf bad=\"x\"/>", ("invalid-x14-cf-formula", "f", "attribute")),
    ("<x14:dxf bad=\"x\"/><xm:f bad=\"x\">A1</xm:f>", ("invalid-x14-cf-order", "cfRule", "f,dxf")),
])
def test_opposite_direction_combined_child_faults_keep_event_precedence(tmp_path, children, expected):
    assert error(corpus(tmp_path / "event-precedence.xlsx", first=extension(owner(rule(children=children))))) == (
        expected[0], PART, expected[1], expected[2]
    )


@pytest.mark.parametrize(("priority", "expected"), [
    ("0", ("invalid-x14-cf-priority", "priority", "0")),
    ("-1", ("invalid-x14-cf-priority", "priority", "-1")),
    ("1.0", ("invalid-x14-cf-priority", "priority", "1.0")),
    ("\u00a01", ("invalid-x14-cf-priority", "priority", "\u00a01")),
    ("2147483648", ("invalid-x14-cf-priority", "priority", "2147483648")),
    ("10000000000", ("invalid-x14-cf-priority", "priority", "10000000000")),
])
def test_priority_semantics_and_numeric_uniqueness(tmp_path, priority, expected):
    assert error(corpus(tmp_path / "priority.xlsx", first=extension(owner(rule(priority=priority))))) == (
        expected[0], PART, expected[1], expected[2]
    )
    duplicate = extension(owner(rule(priority="01")) + owner(rule(priority="+1")))
    assert error(corpus(tmp_path / "duplicate.xlsx", first=duplicate)) == (
        "duplicate-x14-cf-priority", PART, "priority", "1"
    )


@pytest.mark.parametrize(("replacement", "expected"), [
    ('type="cellIs"', ("unsupported-x14-cf-rule-type", "type", "cellIs")),
    ('stopIfTrue="yes"', ("invalid-x14-cf-boolean", "stopIfTrue", "yes")),
    ('id="not-a-guid"', ("invalid-x14-cf-id", "id", "not-a-guid")),
])
def test_type_boolean_and_guid_semantic_negatives(tmp_path, replacement, expected):
    source = rule()
    if replacement.startswith("type"):
        body = source.replace('type="expression"', replacement)
    elif replacement.startswith("stop"):
        body = source.replace(' id="', ' ' + replacement + ' id="')
    else:
        body = source.replace('id="' + GUID + '"', replacement)
    assert error(corpus(tmp_path / "rule-semantics.xlsx", first=extension(owner(body)))) == (
        expected[0], PART, expected[1], expected[2]
    )


@pytest.mark.parametrize(("foreign", "expected_tag"), [
    ("<x14:foreign/>", f"{{{X14}}}foreign"),
    ("<xm:foreign/>", f"{{{XM}}}foreign"),
])
def test_foreign_x14_and_xm_direct_rule_children_are_not_projected(tmp_path, foreign, expected_tag):
    children = "<xm:f>A1</xm:f><x14:dxf/>" + foreign
    assert error(corpus(tmp_path / "foreign-child.xlsx", first=extension(owner(rule(children=children))))) == (
        "unknown-x14-cf-child", PART, "tag", expected_tag
    )


@pytest.mark.parametrize("sqref", [
    '<xm:sqref bad="x"> malformed </xm:sqref>',
    '<xm:sqref/><xm:sqref>duplicate</xm:sqref>',
    '<xm:sqref>A9</xm:sqref>',
])
def test_sqref_before_and_between_rules_is_ignored_without_changing_projection(tmp_path, sqref):
    first = '<x14:conditionalFormatting>' + sqref + rule(priority="7", formula="A6&gt;0") + sqref + rule(priority="2", formula="B10=1") + '</x14:conditionalFormatting>'
    baseline = '<x14:conditionalFormatting>' + rule(priority="7", formula="A6&gt;0") + rule(priority="2", formula="B10=1") + '</x14:conditionalFormatting>'
    actual = read_worksheet_x14_cf_rule_envelope(corpus(tmp_path / "sqref.xlsx", first=extension(first)))
    expected = read_worksheet_x14_cf_rule_envelope(corpus(tmp_path / "baseline.xlsx", first=extension(baseline)))
    assert actual == expected
    assert [(item.owner_path, item.document_order, item.priority, item.formula) for item in actual.worksheets[0].containers[0].rules] == [
        (PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[1]", 1, 7, "A6>0"),
        (PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]/cfRule[2]", 2, 2, "B10=1"),
    ]


@pytest.mark.parametrize("before, between", [
    ("", ""),
    ('<xm:sqref bad="x">malformed</xm:sqref>', ""),
    ("", '<xm:sqref/><xm:sqref>duplicate</xm:sqref>'),
    ('<xm:sqref/>', '<xm:sqref bad="x">misplaced</xm:sqref>'),
])
def test_sqref_positions_preserve_earliest_invalid_rule_error(tmp_path, before, between):
    missing_id = rule(priority="2").replace(' id="' + GUID + '"', "")
    baseline = '<x14:conditionalFormatting>' + rule(priority="0") + missing_id + '</x14:conditionalFormatting>'
    actual = '<x14:conditionalFormatting>' + before + rule(priority="0") + between + missing_id + '</x14:conditionalFormatting>'
    expected = error(corpus(tmp_path / "sqref-invalid-baseline.xlsx", first=extension(baseline)))
    assert expected == ("invalid-x14-cf-priority", PART, "priority", "0")
    assert error(corpus(tmp_path / "sqref-invalid-actual.xlsx", first=extension(actual))) == expected


@pytest.mark.parametrize("before, between", [
    ('<xm:sqref bad="x">malformed</xm:sqref>', ""),
    ("", '<xm:sqref/><xm:sqref>duplicate</xm:sqref>'),
])
def test_sqref_positions_preserve_earliest_invalid_formula_error(tmp_path, before, between):
    invalid_formula = rule(priority="1", children="<xm:f/><x14:dxf/>")
    later_priority_fault = rule(priority="0")
    baseline = (
        "<x14:conditionalFormatting>"
        + invalid_formula
        + later_priority_fault
        + "</x14:conditionalFormatting>"
    )
    actual = (
        "<x14:conditionalFormatting>"
        + before
        + invalid_formula
        + between
        + later_priority_fault
        + "</x14:conditionalFormatting>"
    )
    expected = error(corpus(tmp_path / "sqref-formula-baseline.xlsx", first=extension(baseline)))
    assert expected == ("invalid-x14-cf-formula", PART, "f", "text")
    assert error(corpus(tmp_path / "sqref-formula-actual.xlsx", first=extension(actual))) == expected


def test_sqref_between_rules_preserves_earlier_missing_attribute_error(tmp_path):
    missing_id = rule(priority="1").replace(' id="' + GUID + '"', "")
    baseline = '<x14:conditionalFormatting>' + missing_id + rule(priority="0") + '</x14:conditionalFormatting>'
    actual = ('<x14:conditionalFormatting><xm:sqref/><xm:sqref bad="x">reordered</xm:sqref>'
              + missing_id + '<xm:sqref>between</xm:sqref>' + rule(priority="0")
              + '</x14:conditionalFormatting>')
    expected = error(corpus(tmp_path / "sqref-missing-baseline.xlsx", first=extension(baseline)))
    assert expected == ("invalid-x14-cf-cardinality", PART, "attribute", "id")
    assert error(corpus(tmp_path / "sqref-missing-actual.xlsx", first=extension(actual))) == expected


def test_foreign_direct_child_precedes_combined_x2a_rule_faults(tmp_path):
    combined = ('<x14:conditionalFormatting><x14:cfRule type="expression" priority="0">'
                '<xm:f>A1</xm:f><x14:dxf/><foreign/></x14:cfRule></x14:conditionalFormatting>')
    assert error(corpus(tmp_path / "x1-x2a-precedence.xlsx", first=extension(combined))) == (
        "unknown-x14-cf-child", PART, "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}foreign"
    )


def test_x1_failure_precedes_x2a_and_second_sheet_failure_is_atomic(tmp_path):
    x1_first = '<x14:conditionalFormatting><x14:cfRule/></x14:conditionalFormatting>'
    assert error(corpus(tmp_path / "x1-first.xlsx", first=extension(x1_first))) == (
        "invalid-x14-cf-cardinality", PART, "attribute", "id"
    )
    assert error(corpus(
        tmp_path / "second-sheet.xlsx",
        first=extension(owner(rule(priority="1"))),
        second=extension(owner(rule(priority="0"))),
    )) == ("invalid-x14-cf-priority", SECOND_PART, "priority", "0")


def test_pathlike_topology_identity_and_single_xml_parse_per_worksheet(monkeypatch, tmp_path):
    class CountedPath:
        def __init__(self, value):
            self.value = value
            self.calls = 0

        def __fspath__(self):
            self.calls += 1
            return self.value

    path = corpus(
        tmp_path / "io.xlsx",
        first=extension(owner(rule(priority="1"))),
        second=extension(owner(rule(priority="2"))),
    )
    counted = CountedPath(str(path))
    original = reader.ET.fromstring
    calls = []

    def parse(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(reader.ET, "fromstring", parse)
    read_worksheet_x14_cf_rule_envelope(counted)
    assert counted.calls == 1
    assert sum(payload.startswith(b"<worksheet") for payload in calls) == 2
    sentinel = RuntimeError("topology")
    monkeypatch.setattr(reader, "read_workbook_topology", lambda value: (_ for _ in ()).throw(sentinel))
    with pytest.raises(RuntimeError) as captured:
        read_worksheet_x14_cf_rule_envelope(str(path))
    assert captured.value is sentinel
