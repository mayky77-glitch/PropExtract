"""Frozen direct-tree matrix for X14 CF owner-tag recognition."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as reader
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError,
    WorkbookX14CfOwnerTopology,
    X14CfContainerOwner,
    WorksheetX14CfOwnerTopology,
    read_worksheet_x14_cf_owner_topology,
)
from rns_import_server.opc_part_uri import CanonicalPartURI
from rns_import_server.opc_workbook_topology import WorksheetDescriptor
from tests.opc_worksheet_x14_cf_owner_fixture_factory import CF_URI, DV_URI, X14, XM, package, worksheet


PART = "xl/worksheets/first.xml"
FOREIGN = "urn:owner-tag-v2-foreign"
OWNED = (
    ("conditionalFormattings", "x14", X14, "cf_ext"),
    ("conditionalFormatting", "x14", X14, "forms"),
    ("cfRule", "x14", X14, "form"),
    ("dxf", "x14", X14, "rule"),
    ("f", "xm", XM, "rule"),
    ("sqref", "xm", XM, "form"),
)
DEPTHS = ("worksheet", "wrapper", "extlst", "cf_ext", "dv_ext", "other_ext", "forms", "form", "rule")


def error(path):
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_owner_topology(path)
    return captured.value.as_tuple()


def node(prefix, local, namespace):
    return f'<{prefix}:{local} xmlns:{prefix}="{namespace}"/>'


def cf(inner=""):
    return (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>'
            f'<x14:conditionalFormatting>{inner}</x14:conditionalFormatting>'
            '</x14:conditionalFormattings></ext></extLst>')


def direct_tree(depth, value):
    return {
        "worksheet": value,
        "wrapper": f"<foreign>{value}</foreign>",
        "extlst": f"<extLst>{value}</extLst>",
        "cf_ext": f'<extLst><ext uri="{CF_URI}">{value}</ext></extLst>',
        "dv_ext": f'<extLst><ext uri="{DV_URI}">{value}</ext></extLst>',
        "other_ext": f'<extLst><ext uri="urn:other">{value}</ext></extLst>',
        "forms": f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>{value}</x14:conditionalFormattings></ext></extLst>',
        "form": cf(value),
        "rule": cf(f"<x14:cfRule>{value}</x14:cfRule>"),
    }[depth]


def legal_tree(local):
    values = {
        "conditionalFormattings": f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>',
        "conditionalFormatting": cf(),
        "cfRule": cf("<x14:cfRule/>"),
        "dxf": cf("<x14:cfRule><x14:dxf/></x14:cfRule>"),
        "f": cf("<x14:cfRule><xm:f/></x14:cfRule>"),
        "sqref": cf("<xm:sqref/>"),
    }
    return values[local]


@pytest.mark.parametrize(("local", "prefix", "namespace", "legal_depth"), OWNED)
def test_each_owned_tag_has_one_legal_parent_and_exact_failure_at_every_other_owner_depth(
        tmp_path, local, prefix, namespace, legal_depth):
    assert len(read_worksheet_x14_cf_owner_topology(
        package(tmp_path / f"legal-{local}.xlsx", sheet_one=worksheet(legal_tree(local)))
    ).worksheets[0].containers) == 1
    value = node(prefix, local, namespace)
    for depth in DEPTHS:
        if depth == legal_depth:
            continue
        expected = ("invalid-x14-cf-parent", PART, "tag", f"{{{namespace}}}{local}")
        if local == "conditionalFormattings" and depth == "other_ext":
            expected = ("unsupported-x14-cf-extension-uri", PART, "uri", "urn:other")
        assert error(package(tmp_path / f"{local}-{depth}.xlsx", sheet_one=worksheet(direct_tree(depth, value)))) == expected


@pytest.mark.parametrize(("local", "prefix", "namespace", "legal_depth"), OWNED)
@pytest.mark.parametrize("variant", ("wrong-case", "foreign", "empty"))
def test_owned_local_namespace_collisions_are_exact_at_its_legal_depth(tmp_path, local, prefix, namespace, legal_depth, variant):
    actual_namespace = {"wrong-case": namespace.upper(), "foreign": FOREIGN, "empty": None}[variant]
    value = f'<{local} xmlns=""/>' if actual_namespace is None else node(prefix, local, actual_namespace)
    body = direct_tree(legal_depth, value)
    detail = local if actual_namespace is None else f"{{{actual_namespace}}}{local}"
    assert error(package(tmp_path / f"namespace-{local}-{variant}.xlsx", sheet_one=worksheet(body))) == (
        "x14-cf-namespace-collision", PART, "tag", detail,
    )


@pytest.mark.parametrize(("local", "prefix", "namespace", "legal_depth"), OWNED)
def test_wrong_local_name_case_is_not_treated_as_an_owned_tag(tmp_path, local, prefix, namespace, legal_depth):
    wrong = node(prefix, local.swapcase(), namespace)
    # At worksheet depth this is deliberately neither an owned tag nor a collision.
    result = read_worksheet_x14_cf_owner_topology(package(
        tmp_path / f"wrong-local-{local}.xlsx", sheet_one=worksheet(wrong)
    ))
    assert result.worksheets[0].containers == ()


@pytest.mark.parametrize(("owner", "body", "detail"), (
    ("extLst", f'<extLst>text<ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "text"),
    ("extLst", f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext>tail</extLst>', "tail"),
    ("ext", f'<extLst><ext uri="{CF_URI}">text<x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "text"),
    ("ext", f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings>tail</ext></extLst>', "tail"),
    ("conditionalFormattings", f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>text<x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "text"),
    ("conditionalFormattings", f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/>tail</x14:conditionalFormattings></ext></extLst>', "tail"),
    ("conditionalFormatting", cf("text<x14:cfRule/>"), "text"),
    ("conditionalFormatting", cf("<x14:cfRule/>tail"), "tail"),
    ("conditionalFormatting", cf("<xm:sqref/>tail"), "tail"),
    ("cfRule", cf("<x14:cfRule>text<xm:f/></x14:cfRule>"), "text"),
    ("cfRule", cf("<x14:cfRule><xm:f/>tail</x14:cfRule>"), "tail"),
    ("cfRule", cf("<x14:cfRule><x14:dxf/>tail</x14:cfRule>"), "tail"),
))
def test_nonwhite_text_and_every_direct_child_tail_are_rejected(tmp_path, owner, body, detail):
    assert error(package(tmp_path / f"content-{owner}-{detail}.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-content", PART, owner, detail,
    )


def test_xml_whitespace_is_valid_and_native_sml_tags_are_unowned(tmp_path):
    body = ('<conditionalFormatting><cfRule><formula>A1</formula></cfRule></conditionalFormatting>'
            '<sheetData><row r="6"><c r="A6"><f>SUM(A1:A5)</f></c></row></sheetData>'
            f'<extLst> \n <ext uri="{CF_URI}"> \t <x14:conditionalFormattings> \n '
            '<x14:conditionalFormatting> \t <x14:cfRule> \n <xm:f/> \r <x14:dxf/> \t </x14:cfRule> '
            '<xm:sqref/> \n </x14:conditionalFormatting> \t </x14:conditionalFormattings> \n </ext> \t </extLst>')
    assert len(read_worksheet_x14_cf_owner_topology(
        package(tmp_path / "whitespace-native.xlsx", sheet_one=worksheet(body))
    ).worksheets[0].containers) == 1


def test_dv_carve_is_exact_and_never_activates_for_other_extension_uris(tmp_path):
    dv_values = '<x14:dataValidations><x14:dataValidation><xm:f>1</xm:f><xm:sqref>A1</xm:sqref></x14:dataValidation></x14:dataValidations>'
    adjacent = f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext><ext uri="{DV_URI}">{dv_values}</ext></extLst>'
    assert len(read_worksheet_x14_cf_owner_topology(
        package(tmp_path / "adjacent.xlsx", sheet_one=worksheet(adjacent))
    ).worksheets[0].containers) == 1
    assert read_worksheet_x14_cf_owner_topology(package(tmp_path / "dv-only.xlsx", sheet_one=worksheet(f'<extLst><ext uri="{DV_URI}">{dv_values}</ext></extLst>'))).worksheets[0].containers == ()
    for uri in (DV_URI.upper(), "urn:unknown", "", "not-a-guid"):
        body = f'<extLst><ext uri="{uri}">{dv_values}</ext></extLst>'
        assert error(package(tmp_path / f"dv-uri-{len(uri)}.xlsx", sheet_one=worksheet(body))) == (
            "invalid-x14-cf-parent", PART, "tag", f"{{{XM}}}f",
        )


@pytest.mark.parametrize("position", ("before", "after"))
def test_dv_carve_does_not_mask_cf_owned_siblings_in_document_order(tmp_path, position):
    dv = '<x14:dataValidations><x14:dataValidation><xm:f>1</xm:f><xm:sqref>A1</xm:sqref></x14:dataValidation></x14:dataValidations>'
    misplaced = '<x14:conditionalFormatting/>'
    children = misplaced + dv if position == "before" else dv + misplaced
    body = f'<extLst><ext uri="{DV_URI}">{children}</ext></extLst>'
    assert error(package(tmp_path / f"dv-sibling-{position}.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{X14}}}conditionalFormatting",
    )


@pytest.mark.parametrize("position", ("before", "after"))
def test_dv_carve_does_not_accept_cf_owned_tag_inside_legal_data_validation(tmp_path, position):
    values = "<xm:f>1</xm:f><xm:sqref>A1</xm:sqref>"
    misplaced = "<x14:conditionalFormatting/>"
    children = misplaced + values if position == "before" else values + misplaced
    body = f'<extLst><ext uri="{DV_URI}"><x14:dataValidations><x14:dataValidation>{children}</x14:dataValidation></x14:dataValidations></ext></extLst>'
    assert error(package(tmp_path / f"dv-nested-{position}.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{X14}}}conditionalFormatting",
    )


@pytest.mark.parametrize("local", ("f", "sqref"))
@pytest.mark.parametrize("uri", (DV_URI.swapcase(), "urn:unknown", "", "not-a-guid"))
def test_dv_carve_requires_exact_uri_for_each_xm_value_without_sibling_masking(tmp_path, local, uri):
    value = f"<xm:{local}>A1</xm:{local}>"
    body = f'<extLst><ext uri="{uri}"><x14:dataValidations><x14:dataValidation>{value}</x14:dataValidation></x14:dataValidations></ext></extLst>'
    assert error(package(tmp_path / f"dv-isolated-{local}-{len(uri)}.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{XM}}}{local}",
    )


def test_document_tier_precedence_and_two_sheet_atomic_failure_are_exact(tmp_path):
    later = cf("<x14:cfRule><xm:f/>tail</x14:cfRule>")
    assert error(package(tmp_path / "tier.xlsx", sheet_one=worksheet("<x14:dxf/>" + later))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{X14}}}dxf",
    )
    assert error(package(tmp_path / "order.xlsx", sheet_one=worksheet(cf("<bad/><x14:cfRule><xm:f/>tail</x14:cfRule>")))) == (
        "unknown-x14-cf-child", PART, "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}bad",
    )
    valid = worksheet(cf())
    invalid = worksheet("<x14:cfRule/>")
    assert error(package(tmp_path / "atomic.xlsx", sheet_one=valid, sheet_two=invalid)) == (
        "invalid-x14-cf-parent", "xl/worksheets/second.xml", "tag", f"{{{X14}}}cfRule",
    )


def test_two_sheet_rows_projection_order_and_all_public_records_are_immutable(tmp_path):
    first = ('<sheetData><row r="6"/><row r="10"/></sheetData>'
             f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>'
             '<x14:conditionalFormatting><x14:cfRule><xm:f>opaque-6</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A6</xm:sqref></x14:conditionalFormatting>'
             '<x14:conditionalFormatting><x14:cfRule><xm:f>opaque-10</xm:f><x14:dxf/></x14:cfRule><xm:sqref>A10</xm:sqref></x14:conditionalFormatting>'
             '</x14:conditionalFormattings></ext></extLst>')
    second = '<sheetData><row r="104"/></sheetData>' + cf('<x14:cfRule><xm:f>lower-priority</xm:f><x14:dxf/></x14:cfRule><xm:sqref>B104</xm:sqref>')
    result = read_worksheet_x14_cf_owner_topology(package(tmp_path / "projection.xlsx", sheet_one=worksheet(first), sheet_two=worksheet(second)))
    assert isinstance(result, WorkbookX14CfOwnerTopology)
    assert tuple(field.name for field in fields(X14CfContainerOwner)) == ("owner_path", "document_order")
    assert tuple(field.name for field in fields(WorksheetX14CfOwnerTopology)) == ("worksheet", "containers")
    assert tuple(field.name for field in fields(WorkbookX14CfOwnerTopology)) == ("worksheets",)
    assert result.worksheets[0].worksheet == WorksheetDescriptor("Первый", 1, "visible", "one", CanonicalPartURI(PART))
    assert result.worksheets[1].worksheet == WorksheetDescriptor("Второй", 2, "visible", "two", CanonicalPartURI("xl/worksheets/second.xml"))
    assert result.worksheets[0].containers == (
        X14CfContainerOwner(PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", 1),
        X14CfContainerOwner(PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]", 2),
    )
    assert result.worksheets[1].containers == (
        X14CfContainerOwner("xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", 1),
    )
    assert asdict(result) == {"worksheets": (
        {"worksheet": {"name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one", "worksheet_part": {"value": PART}}, "containers": ({"owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1}, {"owner_path": PART + "/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]", "document_order": 2})},
        {"worksheet": {"name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two", "worksheet_part": {"value": "xl/worksheets/second.xml"}}, "containers": ({"owner_path": "xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1},)},
    )}
    for instance, attribute, value in ((result, "worksheets", ()), (result.worksheets[0], "containers", ()), (result.worksheets[0].containers[0], "document_order", 2), (result.worksheets[0].worksheet, "name", "changed"), (result.worksheets[0].worksheet.worksheet_part, "value", "changed")):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, attribute, value)
