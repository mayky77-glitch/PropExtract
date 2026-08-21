"""Strict X2b sqref envelope contract and event-order corpus."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as reader
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError, WorkbookX14CfSqrefEnvelope,
    X14CfOwnerSqrefEnvelope, X14CfSqrefRange, WorksheetX14CfSqrefEnvelope,
    read_worksheet_x14_cf_sqref_envelope,
)
from rns_import_server.opc_worksheet_native_cf_reader import read_worksheet_native_cf_container_inventory
from tests.opc_worksheet_native_cf_fixture_factory import package as native_package, worksheet as native_worksheet
from tests.opc_worksheet_x14_cf_sqref_fixture_factory import corpus, extension, owner, rule


PART = "xl/worksheets/first.xml"


def error(path):
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_sqref_envelope(path)
    return captured.value.as_tuple()


def test_projection_public_shape_immutability_and_typed_ranges(tmp_path):
    first = extension(owner(rule(priority="7", formula="A6&gt;0"), sqref="<xm:sqref>$a$6 B10:C10\tXFD1048576</xm:sqref>"))
    second = extension(owner(rule(priority="2", formula="C104&gt;0"), sqref="<xm:sqref>R104:R154</xm:sqref>"))
    result = read_worksheet_x14_cf_sqref_envelope(corpus(tmp_path / "projection.xlsx", first=first, second=second))
    assert isinstance(result, WorkbookX14CfSqrefEnvelope)
    assert tuple(field.name for field in fields(X14CfSqrefRange)) == ("source_token", "start_coordinate", "end_coordinate", "min_row", "min_column", "max_row", "max_column")
    assert tuple(field.name for field in fields(X14CfOwnerSqrefEnvelope)) == ("owner", "rules", "sqref_text", "ranges")
    assert tuple(field.name for field in fields(WorksheetX14CfSqrefEnvelope)) == ("worksheet", "containers")
    group = result.worksheets[0].containers[0]
    assert group.sqref_text == "$a$6 B10:C10\tXFD1048576"
    assert group.ranges == (
        X14CfSqrefRange("$a$6", "A6", "A6", 6, 1, 6, 1),
        X14CfSqrefRange("B10:C10", "B10", "C10", 10, 2, 10, 3),
        X14CfSqrefRange("XFD1048576", "XFD1048576", "XFD1048576", 1048576, 16384, 1048576, 16384),
    )
    assert group.owner.owner_path.endswith("conditionalFormatting[1]")
    assert group.rules[0].formula == "A6>0"
    assert asdict(result)["worksheets"][1]["containers"][0]["ranges"][0]["min_row"] == 104
    for instance, attr in ((result, "worksheets"), (group, "ranges"), (group.ranges[0], "min_row")):
        with pytest.raises(FrozenInstanceError): setattr(instance, attr, None)


@pytest.mark.parametrize("sqref", ("A1", "$A$1:$XFD$1048576", "a1:b2", "A1\tB2\rC3\nD4"))
def test_a1_grammar_accepts_xml_whitespace_and_bounds(tmp_path, sqref):
    result = read_worksheet_x14_cf_sqref_envelope(corpus(tmp_path / "valid.xlsx", first=extension(owner(rule(), sqref=f"<xm:sqref>{sqref}</xm:sqref>"))))
    assert result.worksheets[0].containers[0].ranges


@pytest.mark.parametrize("sqref", (
    "", " ", "A:A", "1:1", "Sheet1!A1", "[book]Sheet1!A1", "A0", "A01", "XFE1", "A1048577",
    "A1:B0", "B2:A2", "A2:A1", "A1:B2:C3", "A1\u00a0B2", "A1\u0085B2", "A1\u2003B2", "A" * 10000, "A" + "9" * 5000,
))
def test_a1_grammar_rejects_noncanonical_tokens(tmp_path, sqref):
    expected = "text" if not sqref.strip(" \t\r\n") else sqref
    assert error(corpus(tmp_path / "bad.xlsx", first=extension(owner(rule(), sqref=f"<xm:sqref>{sqref}</xm:sqref>")))) == (
        "invalid-x14-cf-sqref", PART, "sqref", expected)


@pytest.mark.parametrize(("sqref", "code", "detail"), (
    ("A1 A1", "duplicate-x14-cf-sqref", "A1"),
    ("$A$1 A1", "duplicate-x14-cf-sqref", "A1"),
    ("A1:B2 B2:C3", "overlapping-x14-cf-sqref", "B2:C3"),
    ("A1:C1 B1:B3", "overlapping-x14-cf-sqref", "B1:B3"),
    ("A1:C3 B2", "overlapping-x14-cf-sqref", "B2"),
))
def test_duplicate_and_overlap_geometry(tmp_path, sqref, code, detail):
    assert error(corpus(tmp_path / "overlap.xlsx", first=extension(owner(rule(), sqref=f"<xm:sqref>{sqref}</xm:sqref>")))) == (code, PART, "sqref", detail)


def test_adjacent_ranges_pass(tmp_path):
    result = read_worksheet_x14_cf_sqref_envelope(corpus(tmp_path / "adjacent.xlsx", first=extension(owner(rule(), sqref="<xm:sqref>A1:A2 A3:A4 B1:B2</xm:sqref>"))))
    assert len(result.worksheets[0].containers[0].ranges) == 3


@pytest.mark.parametrize("sqref", ("$a$6 B10:C10 R104:R154", "A1:C3 B4:D5", "XFD1048576"))
def test_typed_geometry_matches_accepted_native_cf_public_api(tmp_path, sqref):
    x14 = read_worksheet_x14_cf_sqref_envelope(corpus(
        tmp_path / "x14.xlsx", first=extension(owner(rule(), sqref=f"<xm:sqref>{sqref}</xm:sqref>"))))
    native = read_worksheet_native_cf_container_inventory(native_package(
        tmp_path / "native.xlsx", sheet_one=native_worksheet(f'<conditionalFormatting sqref="{sqref}"/>')))
    actual = x14.worksheets[0].containers[0].ranges
    expected = native.worksheets[0].containers[0].sqref
    assert tuple((item.start_coordinate, item.end_coordinate, item.min_row, item.min_column, item.max_row, item.max_column) for item in actual) == tuple(
        (item.start_coordinate, item.end_coordinate, item.min_row, item.min_column, item.max_row, item.max_column) for item in expected)


@pytest.mark.parametrize(("children", "expected"), (
    ("", ("invalid-x14-cf-cardinality", "conditionalFormatting", "cfRule")),
    (rule() , ("invalid-x14-cf-cardinality", "conditionalFormatting", "sqref")),
    ("<xm:sqref>A1</xm:sqref>", ("invalid-x14-cf-order", "conditionalFormatting", "cfRule,sqref")),
    ("<xm:sqref>A1</xm:sqref>" + rule(), ("invalid-x14-cf-order", "conditionalFormatting", "cfRule,sqref")),
    (rule() + "<xm:sqref>A1</xm:sqref><xm:sqref>B2</xm:sqref>", ("duplicate-x14-cf-sqref", "sqref", "B2")),
))
def test_owner_cardinality_and_order(tmp_path, children, expected):
    assert error(corpus(tmp_path / "order.xlsx", first=extension(f"<x14:conditionalFormatting>{children}</x14:conditionalFormatting>"))) == (expected[0], PART, expected[1], expected[2])


@pytest.mark.parametrize(("sqref", "detail"), (("<xm:sqref bad=\"x\">A1</xm:sqref>", "attribute"), ("<xm:sqref><bad/></xm:sqref>", "child"), ("<xm:sqref/>", "text")))
def test_first_sqref_is_validated_before_later_owner_faults(tmp_path, sqref, detail):
    body = f"<x14:conditionalFormatting>{rule()}{sqref}<xm:sqref>B2</xm:sqref>{rule(priority='2')}</x14:conditionalFormatting>"
    assert error(corpus(tmp_path / "precedence.xlsx", first=extension(body))) == ("invalid-x14-cf-sqref", PART, "sqref", detail)


def test_invalid_first_sqref_token_precedes_later_duplicate_and_rule_fault(tmp_path):
    body = f"<x14:conditionalFormatting>{rule()}<xm:sqref>A0 A1</xm:sqref><xm:sqref>B2</xm:sqref>{rule(priority='2')}</x14:conditionalFormatting>"
    assert error(corpus(tmp_path / "token-precedence.xlsx", first=extension(body))) == ("invalid-x14-cf-sqref", PART, "sqref", "A0")


def test_earlier_rule_fault_precedes_later_sqref_fault_and_x1_precedes_x2(tmp_path):
    bad_rule = rule(priority="0")
    body = f"<x14:conditionalFormatting>{bad_rule}<xm:sqref bad=\"x\">A1</xm:sqref></x14:conditionalFormatting>"
    assert error(corpus(tmp_path / "rule-first.xlsx", first=extension(body))) == ("invalid-x14-cf-priority", PART, "priority", "0")
    first = extension(owner(rule(), sqref="<xm:sqref>A1</xm:sqref>"))
    second = "<x14:conditionalFormattings/>"
    assert error(corpus(tmp_path / "x1-first.xlsx", first=first, second=second)) == ("invalid-x14-cf-parent", "xl/worksheets/second.xml", "tag", "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}conditionalFormattings")


def test_x14_dv_sqref_remains_unowned_and_reader_is_atomic(monkeypatch, tmp_path):
    dv = '<ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations><x14:dataValidation><xm:sqref bad="x">not-a1</xm:sqref></x14:dataValidation></x14:dataValidations></ext>'
    path = corpus(tmp_path / "dv.xlsx", first=extension(owner(rule())).replace("<extLst>", "<extLst>" + dv))
    counted = type("CountedPath", (), {"calls": 0, "__fspath__": lambda self: setattr(self, "calls", self.calls + 1) or str(path)})()
    original = reader.ET.fromstring; calls=[]
    monkeypatch.setattr(reader.ET, "fromstring", lambda payload: calls.append(payload) or original(payload))
    result = read_worksheet_x14_cf_sqref_envelope(counted)
    assert counted.calls == 1 and len(result.worksheets[0].containers) == 1 and sum(item.startswith(b"<worksheet") for item in calls) == 2


def test_x14_dv_after_owner_sqref_remains_unowned(tmp_path):
    dv = '<ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations><x14:dataValidation><xm:sqref bad="x">not-a1</xm:sqref></x14:dataValidation></x14:dataValidations></ext>'
    result = read_worksheet_x14_cf_sqref_envelope(corpus(
        tmp_path / "dv-after.xlsx", first=extension(owner(rule())).replace("</extLst>", dv + "</extLst>")))
    assert len(result.worksheets[0].containers) == 1


def test_topology_sentinel_identity_and_single_call(monkeypatch, tmp_path):
    sentinel = RuntimeError("topology")
    calls = []
    def fail(path):
        calls.append(path)
        raise sentinel
    monkeypatch.setattr(reader, "read_workbook_topology", fail)
    with pytest.raises(RuntimeError) as captured:
        read_worksheet_x14_cf_sqref_envelope(tmp_path / "not-opened.xlsx")
    assert captured.value is sentinel and calls == [str(tmp_path / "not-opened.xlsx")]


def test_second_sheet_sqref_failure_is_atomic(tmp_path):
    first = extension(owner(rule(), sqref="<xm:sqref>A6</xm:sqref>"))
    second = extension(owner(rule(), sqref="<xm:sqref>A0</xm:sqref>"))
    assert error(corpus(tmp_path / "atomic-second.xlsx", first=first, second=second)) == (
        "invalid-x14-cf-sqref", "xl/worksheets/second.xml", "sqref", "A0")
