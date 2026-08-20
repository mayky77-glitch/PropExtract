from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from rns_import_server.opc_workbook_topology import WorksheetDescriptor
from rns_import_server.opc_part_uri import CanonicalPartURI
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError, WorkbookX14CfOwnerTopology,
    X14CfContainerOwner, read_worksheet_x14_cf_owner_topology,
)
from tests.opc_worksheet_x14_cf_owner_fixture_factory import CF_URI, DV_URI, X14, worksheet, package


def error(path):
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_owner_topology(path)
    return captured.value.as_tuple()


def ext(containers: str) -> str:
    return f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>{containers}</x14:conditionalFormattings></ext></extLst>'


def test_projection_owner_paths_order_and_immutable_records(tmp_path):
    first = ext('<x14:conditionalFormatting><x14:cfRule priority="wrong"><xm:f></xm:f><x14:dxf/></x14:cfRule><xm:sqref>bad</xm:sqref></x14:conditionalFormatting>' * 2)
    result = read_worksheet_x14_cf_owner_topology(package(tmp_path / "ok.xlsx", sheet_one=worksheet('<sheetData><row r="6"/><row r="10"/></sheetData>' + first), sheet_two=worksheet('<sheetData><row r="104"/></sheetData>' + ext('<x14:conditionalFormatting/>'))))
    assert isinstance(result, WorkbookX14CfOwnerTopology)
    assert [item.owner_path for item in result.worksheets[0].containers] == [
        "xl/worksheets/first.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]",
        "xl/worksheets/first.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]",
    ]
    assert [item.document_order for item in result.worksheets[0].containers] == [1, 2]
    assert result.worksheets[1].containers[0].document_order == 1
    assert asdict(result)["worksheets"][0]["worksheet"]["name"] == "Первый"
    with pytest.raises(FrozenInstanceError): result.worksheets[0].containers[0].owner_path = "no"
    with pytest.raises(FrozenInstanceError): result.worksheets[0].containers = ()
    with pytest.raises(FrozenInstanceError): result.worksheets = ()


@pytest.mark.parametrize(("body", "expected"), [
    ('<x14:cfRule/>', "invalid-x14-cf-parent"),
    ('<x14:conditionalFormatting/>', "invalid-x14-cf-parent"),
    ('<x14:conditionalFormattings/>', "invalid-x14-cf-parent"),
    ('<x14:conditionalFormatting><x14:cfRule><x14:dxf><xm:f/></x14:dxf></x14:cfRule></x14:conditionalFormatting>', "invalid-x14-cf-parent"),
    ('<conditionalFormatting xmlns=""/>', "x14-cf-namespace-collision"),
    ('<x:cfRule xmlns:x="urn:wrong"/>', "x14-cf-namespace-collision"),
])
def test_owned_placement_and_namespace_collisions(tmp_path, body, expected):
    assert error(package(tmp_path / "bad.xlsx", sheet_one=worksheet(body)))[0] == expected


@pytest.mark.parametrize(("body", "expected"), [
    (f'<extLst><ext uri="{CF_URI.lower()}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "unsupported-x14-cf-extension-uri"),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings/></ext></extLst>', "invalid-x14-cf-cardinality"),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "duplicate-x14-cf-extension"),
    (f'<extLst extra="x"><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "unknown-x14-cf-attribute"),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting><x14:wat/></x14:conditionalFormatting></x14:conditionalFormattings></ext></extLst>', "unknown-x14-cf-child"),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>text<x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "invalid-x14-cf-content"),
])
def test_chain_cardinality_and_tier_two_faults(tmp_path, body, expected):
    assert error(package(tmp_path / "bad.xlsx", sheet_one=worksheet(body)))[0] == expected


def test_realistic_dv_is_carved_but_malformed_dv_is_not(tmp_path):
    dv = f'<extLst><ext uri="{DV_URI}"><x14:dataValidations><xm:sqref>A1</xm:sqref><xm:f>1</xm:f></x14:dataValidations></ext></extLst>'
    assert read_worksheet_x14_cf_owner_topology(package(tmp_path / "dv.xlsx", sheet_one=worksheet(dv))).worksheets[0].containers == ()
    assert error(package(tmp_path / "bad-dv.xlsx", sheet_one=worksheet(f'<extLst><ext uri="wrong"><x14:dataValidations><xm:sqref>A1</xm:sqref></x14:dataValidations></ext></extLst>')))[0] == "invalid-x14-cf-parent"


def test_native_cf_and_sml_formula_remain_opaque(tmp_path):
    body = '<conditionalFormatting sqref="A1"><cfRule><f>bad</f></cfRule></conditionalFormatting>'
    assert read_worksheet_x14_cf_owner_topology(package(tmp_path / "native.xlsx", sheet_one=worksheet(body))).worksheets[0].containers == ()
