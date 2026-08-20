from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

import rns_import_server.opc_worksheet_x14_cf_reader as reader
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


@pytest.mark.parametrize("mutation", [
    '<xm:sqref>A6</xm:sqref><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule>',
    '<x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><x14:dxf/><xm:f>x</xm:f></x14:cfRule><xm:sqref>A6</xm:sqref>',
    '<x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f></x14:cfRule><xm:sqref>A6</xm:sqref>',
])
def test_order_and_cardinality(tmp_path, mutation):
    result = error(package(tmp_path / "order.xlsx", sheet_one=worksheet(envelope(f'<x14:conditionalFormatting>{mutation}</x14:conditionalFormatting>'))))
    assert result[0] in {"invalid-x14-cf-order", "invalid-x14-cf-cardinality"}


def test_duplicate_priority_and_sibling_x14_dv_coexist(tmp_path):
    body = envelope(container(6, 1) + container(10, 1)) + '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations/></ext></extLst>'
    assert error(package(tmp_path / "duplicate.xlsx", sheet_one=worksheet(body))) == (
        "duplicate-x14-cf-priority", "xl/worksheets/first.xml", "priority", "1",
    )
    valid = envelope(container(6, 1)) + '<extLst><ext uri="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"><x14:dataValidations/></ext></extLst>'
    assert len(read_worksheet_x14_cf_envelope(package(tmp_path / "dv.xlsx", sheet_one=worksheet(valid))).worksheets[0].containers) == 1


@pytest.mark.parametrize(("body", "code"), [
    ('<extLst bad="x"><ext uri="' + URI + '"><x14:conditionalFormattings/></ext></extLst>', "unknown-x14-cf-attribute"),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings bad="x"/></ext></extLst>', "unknown-x14-cf-attribute"),
    ('<extLst><ext uri="' + URI + '"><x14:conditionalFormattings><bad/></x14:conditionalFormattings></ext></extLst>', "unknown-x14-cf-child"),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="0" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), "invalid-x14-cf-priority"),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id=" "><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), "invalid-x14-cf-id"),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), "invalid-x14-cf-cardinality"),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f bad="x">x</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), "unknown-x14-cf-attribute"),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf bad="x"/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), "unknown-x14-cf-attribute"),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf><x14:bad/></x14:dxf></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'), "unknown-x14-cf-child"),
    (envelope('<x14:conditionalFormatting><x14:cfRule type="expression" priority="1" stopIfTrue="true" id="x"><xm:f>x</xm:f><x14:dxf/></x14:cfRule><xm:sqref bad="x">A6</xm:sqref></x14:conditionalFormatting>'), "unknown-x14-cf-attribute"),
])
def test_adversarial_semantic_matrix(tmp_path, body, code):
    assert error(package(tmp_path / "matrix.xlsx", sheet_one=worksheet(body)))[0] == code


@pytest.mark.parametrize("payload", [
    b"",
    b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
    b"<notWorksheet/>",
])
def test_xml_and_root_boundaries(tmp_path, payload):
    result = error(package(tmp_path / "xml.xlsx", sheet_one=payload))
    assert result[0] in {"malformed-worksheet-xml", "invalid-worksheet-root"}


def test_exact_parse_count_per_topology_worksheet(monkeypatch, tmp_path):
    original = reader.ET.fromstring
    calls = []

    def counted(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(reader.ET, "fromstring", counted)
    read_worksheet_x14_cf_envelope(package(tmp_path / "count.xlsx", sheet_one=worksheet(envelope(container(6, 1)))))
    assert sum(b"<worksheet" in payload for payload in calls) == 2


def test_pathlike_called_once_and_topology_identity(monkeypatch, tmp_path):
    sentinel = RuntimeError("topology")
    monkeypatch.setattr(reader, "read_workbook_topology", lambda path: (_ for _ in ()).throw(sentinel))
    with pytest.raises(RuntimeError) as captured:
        read_worksheet_x14_cf_envelope(tmp_path / "missing.xlsx")
    assert captured.value is sentinel
