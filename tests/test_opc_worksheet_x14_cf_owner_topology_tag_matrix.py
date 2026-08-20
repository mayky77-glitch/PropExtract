from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as owner_topology
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError,
    WorkbookX14CfOwnerTopology,
    X14CfContainerOwner,
    read_worksheet_x14_cf_owner_topology,
)
from tests.opc_worksheet_x14_cf_owner_fixture_factory import CF_URI, DV_URI, X14, XM, package, worksheet


PART = "xl/worksheets/first.xml"
_OWNED = (
    ("conditionalFormattings", "x14", X14),
    ("conditionalFormatting", "x14", X14),
    ("cfRule", "x14", X14),
    ("dxf", "x14", X14),
    ("f", "xm", XM),
    ("sqref", "xm", XM),
)


def error(path):
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_owner_topology(path)
    return captured.value.as_tuple()


def tag(prefix, local, namespace):
    return f'<{prefix}:{local} xmlns:{prefix}="{namespace}"/>'


def legal_tree(inner=""):
    return (
        f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>'
        f'<x14:conditionalFormatting>{inner}</x14:conditionalFormatting>'
        '</x14:conditionalFormattings></ext></extLst>'
    )


@pytest.mark.parametrize(("local", "prefix", "namespace", "body"), [
    ("conditionalFormattings", "x14", X14, f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>'),
    ("conditionalFormatting", "x14", X14, legal_tree()),
    ("cfRule", "x14", X14, legal_tree('<x14:cfRule/>')),
    ("dxf", "x14", X14, legal_tree('<x14:cfRule><x14:dxf/></x14:cfRule>')),
    ("f", "xm", XM, legal_tree('<x14:cfRule><xm:f/></x14:cfRule>')),
    ("sqref", "xm", XM, legal_tree('<xm:sqref/>')),
])
def test_each_owned_tag_accepts_only_its_legal_parent(tmp_path, local, prefix, namespace, body):
    result = read_worksheet_x14_cf_owner_topology(package(tmp_path / f"legal-{local}.xlsx", sheet_one=worksheet(body)))
    assert len(result.worksheets[0].containers) == 1


@pytest.mark.parametrize(("local", "prefix", "namespace", "context"), [
    ("conditionalFormattings", "x14", X14, "worksheet"),
    ("conditionalFormattings", "x14", X14, "wrapper"),
    ("conditionalFormattings", "x14", X14, "extension"),
    ("conditionalFormattings", "x14", X14, "formattings"),
    ("conditionalFormattings", "x14", X14, "formatting"),
    ("conditionalFormattings", "x14", X14, "rule"),
    ("conditionalFormatting", "x14", X14, "worksheet"),
    ("conditionalFormatting", "x14", X14, "wrapper"),
    ("conditionalFormatting", "x14", X14, "extension"),
    ("conditionalFormatting", "x14", X14, "formatting"),
    ("conditionalFormatting", "x14", X14, "rule"),
    ("cfRule", "x14", X14, "worksheet"),
    ("cfRule", "x14", X14, "wrapper"),
    ("cfRule", "x14", X14, "extension"),
    ("cfRule", "x14", X14, "formattings"),
    ("cfRule", "x14", X14, "rule"),
    ("dxf", "x14", X14, "worksheet"),
    ("dxf", "x14", X14, "wrapper"),
    ("dxf", "x14", X14, "extension"),
    ("dxf", "x14", X14, "formattings"),
    ("dxf", "x14", X14, "formatting"),
    ("f", "xm", XM, "worksheet"),
    ("f", "xm", XM, "wrapper"),
    ("f", "xm", XM, "extension"),
    ("f", "xm", XM, "formattings"),
    ("f", "xm", XM, "formatting"),
    ("sqref", "xm", XM, "worksheet"),
    ("sqref", "xm", XM, "wrapper"),
    ("sqref", "xm", XM, "extension"),
    ("sqref", "xm", XM, "formattings"),
    ("sqref", "xm", XM, "rule"),
])
def test_owned_tags_fail_at_worksheet_wrapper_and_every_wrong_owner_depth(tmp_path, local, prefix, namespace, context):
    value = tag(prefix, local, namespace)
    bodies = {
        "worksheet": value,
        "wrapper": f"<arbitrary>{value}</arbitrary>",
        "extension": f'<extLst><ext uri="{CF_URI}">{value}</ext></extLst>',
        "formattings": legal_tree(f'<x14:conditionalFormattings>{value}</x14:conditionalFormattings>'),
        "formatting": legal_tree(value),
        "rule": legal_tree(f'<x14:cfRule>{value}</x14:cfRule>'),
    }
    actual = error(package(tmp_path / f"wrong-{local}-{context}.xlsx", sheet_one=worksheet(bodies[context])))
    if local == "conditionalFormattings" and context == "extension":
        assert actual == ("invalid-x14-cf-cardinality", PART, "conditionalFormattings", "conditionalFormatting")
    elif context == "formattings" and local in ("cfRule", "dxf", "f", "sqref"):
        assert actual == ("invalid-x14-cf-parent", PART, "tag", f"{{{X14}}}conditionalFormattings")
    else:
        assert actual == ("invalid-x14-cf-parent", PART, "tag", f"{{{namespace}}}{local}")


@pytest.mark.parametrize(("local", "prefix", "namespace"), _OWNED)
@pytest.mark.parametrize(("variant", "actual_namespace"), [
    ("wrong-case", X14.upper()),
    ("foreign", "urn:foreign"),
    ("empty", None),
])
def test_each_owned_local_rejects_wrong_case_foreign_and_empty_namespaces(tmp_path, local, prefix, namespace, variant, actual_namespace):
    if variant == "wrong-case" and prefix == "xm":
        actual_namespace = XM.upper()
    if actual_namespace is None:
        value = f'<{local} xmlns=""/>'
        expected = local
    else:
        value = tag(prefix, local, actual_namespace)
        expected = f"{{{actual_namespace}}}{local}"
    assert error(package(tmp_path / f"namespace-{local}-{variant}.xlsx", sheet_one=worksheet(value))) == (
        "x14-cf-namespace-collision", PART, "tag", expected,
    )


@pytest.mark.parametrize("uri", [CF_URI.lower(), CF_URI.swapcase()])
def test_conditional_formatting_extension_uri_is_exact_case_sensitive(tmp_path, uri):
    body = f'<extLst><ext uri="{uri}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>'
    assert error(package(tmp_path / "wrong-uri.xlsx", sheet_one=worksheet(body))) == (
        "unsupported-x14-cf-extension-uri", PART, "uri", uri,
    )


def test_direct_sibling_data_validation_extension_is_opaque_but_cf_tags_inside_it_fail(tmp_path):
    accepted = f'<extLst><ext uri="{DV_URI}"><x14:dataValidations><x14:dataValidation><xm:f>1</xm:f><xm:sqref>A1</xm:sqref></x14:dataValidation></x14:dataValidations></ext></extLst>'
    assert read_worksheet_x14_cf_owner_topology(package(tmp_path / "dv-ok.xlsx", sheet_one=worksheet(accepted))).worksheets[0].containers == ()
    rejected = f'<extLst><ext uri="{DV_URI}"><x14:dataValidations><x14:dataValidation><x14:cfRule/></x14:dataValidation></x14:dataValidations></ext></extLst>'
    assert error(package(tmp_path / "dv-cf.xlsx", sheet_one=worksheet(rejected))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{X14}}}cfRule",
    )


@pytest.mark.parametrize(("owner", "body", "detail"), [
    ("ext", f'<extLst><ext uri="{CF_URI}">text<x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "text"),
    ("conditionalFormattings", f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>text<x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', "text"),
    ("conditionalFormatting", legal_tree('text<x14:cfRule/>'), "text"),
    ("cfRule", legal_tree('<x14:cfRule>text<xm:f/></x14:cfRule>'), "text"),
    ("ext", f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings>tail</ext></extLst>', "tail"),
    ("conditionalFormattings", f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/>tail</x14:conditionalFormattings></ext></extLst>', "tail"),
    ("conditionalFormatting", legal_tree('<x14:cfRule/>tail'), "tail"),
    ("cfRule", legal_tree('<x14:cfRule><xm:f/>tail</x14:cfRule>'), "tail"),
])
def test_all_owned_mixed_content_boundaries_and_direct_child_tails(tmp_path, owner, body, detail):
    assert error(package(tmp_path / f"mixed-{owner}-{detail}.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-content", PART, owner, detail,
    )


def test_tier_and_document_precedence_are_exact(tmp_path):
    body = '<x14:dxf/>' + legal_tree('<x14:cfRule><xm:f/>tail</x14:cfRule>')
    assert error(package(tmp_path / "tier-one.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{X14}}}dxf",
    )
    body = legal_tree('<x14:wat/><x14:cfRule><xm:f/>tail</x14:cfRule>')
    assert error(package(tmp_path / "document-order.xlsx", sheet_one=worksheet(body))) == (
        "unknown-x14-cf-child", PART, "tag", f"{{{X14}}}wat",
    )


def test_two_sheet_projection_rows_and_immutable_records_are_frozen(tmp_path):
    body = '<sheetData><row r="6"/><row r="10"/></sheetData>' + legal_tree('<x14:cfRule><xm:f/><x14:dxf/></x14:cfRule>')
    second = '<sheetData><row r="104"/></sheetData>' + legal_tree('<xm:sqref/>')
    result = read_worksheet_x14_cf_owner_topology(package(tmp_path / "projection.xlsx", sheet_one=worksheet(body), sheet_two=worksheet(second)))
    assert isinstance(result, WorkbookX14CfOwnerTopology)
    assert asdict(result) == {
        "worksheets": (
            {"worksheet": {"name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one", "worksheet_part": {"value": "xl/worksheets/first.xml"}}, "containers": ({"owner_path": "xl/worksheets/first.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1},)},
            {"worksheet": {"name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two", "worksheet_part": {"value": "xl/worksheets/second.xml"}}, "containers": ({"owner_path": "xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1},)},
        ),
    }
    assert tuple(field.name for field in fields(X14CfContainerOwner)) == ("owner_path", "document_order")
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers[0].document_order = 2
    with pytest.raises(FrozenInstanceError):
        result.worksheets = ()


def test_reader_still_parses_each_worksheet_once(monkeypatch, tmp_path):
    original = owner_topology.ET.fromstring
    calls = []
    def counted(payload):
        calls.append(payload)
        return original(payload)
    monkeypatch.setattr(owner_topology.ET, "fromstring", counted)
    read_worksheet_x14_cf_owner_topology(package(tmp_path / "single-parse.xlsx"))
    assert sum(payload.startswith(b"<worksheet") for payload in calls) == 2
