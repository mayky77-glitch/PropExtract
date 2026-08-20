from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as owner_topology
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
    assert tuple(field.name for field in fields(X14CfContainerOwner)) == ("owner_path", "document_order")
    assert tuple(field.name for field in fields(owner_topology.WorksheetX14CfOwnerTopology)) == ("worksheet", "containers")
    assert tuple(field.name for field in fields(WorkbookX14CfOwnerTopology)) == ("worksheets",)
    assert tuple(field.name for field in fields(OPCWorksheetX14CfOwnerTopologyError)) == ("code", "subject", "field", "detail")
    with pytest.raises(FrozenInstanceError): result.worksheets[0].containers[0].owner_path = "no"
    with pytest.raises(FrozenInstanceError): result.worksheets[0].containers = ()
    with pytest.raises(FrozenInstanceError): result.worksheets = ()


@pytest.mark.parametrize(("body", "expected"), [
    ('<x14:cfRule/>', ("invalid-x14-cf-parent", "tag", f"{{{X14}}}cfRule")),
    ('<x14:conditionalFormatting/>', ("invalid-x14-cf-parent", "tag", f"{{{X14}}}conditionalFormatting")),
    ('<x14:conditionalFormattings/>', ("invalid-x14-cf-parent", "tag", f"{{{X14}}}conditionalFormattings")),
    ('<x14:conditionalFormatting><x14:cfRule><x14:dxf><xm:f/></x14:dxf></x14:cfRule></x14:conditionalFormatting>', ("invalid-x14-cf-parent", "tag", f"{{{X14}}}conditionalFormatting")),
    ('<conditionalFormatting xmlns=""/>', ("x14-cf-namespace-collision", "tag", "conditionalFormatting")),
    ('<x:cfRule xmlns:x="urn:wrong"/>', ("x14-cf-namespace-collision", "tag", "{urn:wrong}cfRule")),
])
def test_owned_placement_and_namespace_collisions(tmp_path, body, expected):
    assert error(package(tmp_path / "bad.xlsx", sheet_one=worksheet(body))) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


@pytest.mark.parametrize(("body", "expected"), [
    (f'<extLst><ext uri="{CF_URI.lower()}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', ("unsupported-x14-cf-extension-uri", "uri", CF_URI.lower())),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings/></ext></extLst>', ("invalid-x14-cf-cardinality", "conditionalFormattings", "conditionalFormatting")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', ("duplicate-x14-cf-extension", "uri", CF_URI)),
    (f'<extLst extra="x"><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', ("unknown-x14-cf-attribute", "attribute", "extra")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting><x14:wat/></x14:conditionalFormatting></x14:conditionalFormattings></ext></extLst>', ("unknown-x14-cf-child", "tag", f"{{{X14}}}wat")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>text<x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', ("invalid-x14-cf-content", "conditionalFormattings", "text")),
])
def test_chain_cardinality_and_tier_two_faults(tmp_path, body, expected):
    assert error(package(tmp_path / "bad.xlsx", sheet_one=worksheet(body))) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


def test_realistic_dv_is_carved_but_malformed_dv_is_not(tmp_path):
    dv = f'<extLst><ext uri="{DV_URI}"><x14:dataValidations><xm:sqref>A1</xm:sqref><xm:f>1</xm:f></x14:dataValidations></ext></extLst>'
    assert read_worksheet_x14_cf_owner_topology(package(tmp_path / "dv.xlsx", sheet_one=worksheet(dv))).worksheets[0].containers == ()
    assert error(package(tmp_path / "bad-dv.xlsx", sheet_one=worksheet(f'<extLst><ext uri="wrong"><x14:dataValidations><xm:sqref>A1</xm:sqref></x14:dataValidations></ext></extLst>'))) == (
        "invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.microsoft.com/office/excel/2006/main}sqref",
    )


def test_native_cf_and_sml_formula_remain_opaque(tmp_path):
    body = '<conditionalFormatting sqref="A1"><cfRule><f>bad</f></cfRule></conditionalFormatting>'
    assert read_worksheet_x14_cf_owner_topology(package(tmp_path / "native.xlsx", sheet_one=worksheet(body))).worksheets[0].containers == ()


def test_full_asdict_projection_is_frozen(tmp_path):
    result = read_worksheet_x14_cf_owner_topology(package(
        tmp_path / "projection.xlsx",
        sheet_one=worksheet('<sheetData><row r="6"/><row r="10"/></sheetData>' + ext('<x14:conditionalFormatting/><x14:conditionalFormatting/>')),
        sheet_two=worksheet('<sheetData><row r="104"/></sheetData>' + ext('<x14:conditionalFormatting/>')),
    ))
    assert asdict(result) == {
        "worksheets": (
            {"worksheet": {"name": "Первый", "sheet_id": 1, "state": "visible", "relationship_id": "one", "worksheet_part": {"value": "xl/worksheets/first.xml"}}, "containers": (
                {"owner_path": "xl/worksheets/first.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1},
                {"owner_path": "xl/worksheets/first.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[2]", "document_order": 2},
            )},
            {"worksheet": {"name": "Второй", "sheet_id": 2, "state": "visible", "relationship_id": "two", "worksheet_part": {"value": "xl/worksheets/second.xml"}}, "containers": (
                {"owner_path": "xl/worksheets/second.xml/worksheet/extLst[1]/ext[1]/conditionalFormattings[1]/conditionalFormatting[1]", "document_order": 1},
            )},
        ),
    }


@pytest.mark.parametrize("body", [
    '<extLst><ext uri="wrong"><x14:dataValidations><x14:dataValidation><xm:f>x</xm:f><xm:sqref>A1</xm:sqref></x14:dataValidation></x14:dataValidations></ext></extLst>',
    f'<extLst><ext uri="{DV_URI}" extra="x"><x14:dataValidations><x14:dataValidation><xm:f>x</xm:f></x14:dataValidation></x14:dataValidations></ext></extLst>',
    f'<extLst><ext uri="{DV_URI}"><outer><x14:dataValidations><x14:dataValidation><xm:f>x</xm:f></x14:dataValidation></x14:dataValidations></outer></ext></extLst>',
    f'<outer><extLst><ext uri="{DV_URI}"><x14:dataValidations><x14:dataValidation><xm:f>x</xm:f></x14:dataValidation></x14:dataValidations></ext></extLst></outer>',
])
def test_only_complete_direct_dv_ancestry_is_opaque(tmp_path, body):
    assert error(package(tmp_path / "near-dv.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.microsoft.com/office/excel/2006/main}f",
    )


def test_complete_dv_carves_only_xm_formula_and_sqref_descendants(tmp_path):
    body = f'<extLst><ext uri="{DV_URI}"><x14:dataValidations><x14:dataValidation><x14:conditionalFormatting><xm:f>x</xm:f></x14:conditionalFormatting></x14:dataValidation></x14:dataValidations></ext></extLst>'
    assert error(package(tmp_path / "dv-opaque.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", f"{{{X14}}}conditionalFormatting",
    )


@pytest.mark.parametrize(("body", "expected"), [
    (f'<extLst><ext uri="{CF_URI}"><conditionalFormatting/></ext></extLst>', ("x14-cf-namespace-collision", "tag", f"{{http://schemas.openxmlformats.org/spreadsheetml/2006/main}}conditionalFormatting")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', ("x14-cf-namespace-collision", "tag", f"{{http://schemas.openxmlformats.org/spreadsheetml/2006/main}}conditionalFormatting")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><foreign:conditionalFormatting xmlns:foreign="urn:foreign"/></x14:conditionalFormattings></ext></extLst>', ("x14-cf-namespace-collision", "tag", "{urn:foreign}conditionalFormatting")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting><foreign:f xmlns:foreign="urn:foreign"/></x14:conditionalFormatting></x14:conditionalFormattings></ext></extLst>', ("x14-cf-namespace-collision", "tag", "{urn:foreign}f")),
])
def test_namespace_collisions_at_each_owned_depth(tmp_path, body, expected):
    assert error(package(tmp_path / "collision.xlsx", sheet_one=worksheet(body))) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


@pytest.mark.parametrize(("body", "expected"), [
    (f'<extLst>text<ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', ("invalid-x14-cf-content", "extLst", "text")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext>tail</extLst>', ("invalid-x14-cf-content", "extLst", "tail")),
    (f'<extLst><ext uri="{CF_URI}">text<x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>', ("invalid-x14-cf-content", "ext", "text")),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/>tail</x14:conditionalFormattings></ext></extLst>', ("invalid-x14-cf-content", "conditionalFormattings", "tail")),
])
def test_owned_mixed_content_exact_tuples(tmp_path, body, expected):
    assert error(package(tmp_path / "mixed.xlsx", sheet_one=worksheet(body))) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


@pytest.mark.parametrize("rule", [
    '<x14:cfRule>text</x14:cfRule>',
    '<x14:cfRule><xm:f/>tail</x14:cfRule>',
    '<x14:cfRule><x14:dxf/>tail</x14:cfRule>',
    '<x14:cfRule><xm:f/>first-tail<x14:dxf/>later-tail</x14:cfRule>',
])
def test_rule_owned_mixed_content_exact_tuples(tmp_path, rule):
    assert error(package(tmp_path / "rule-mixed.xlsx", sheet_one=worksheet(ext(f'<x14:conditionalFormatting>{rule}</x14:conditionalFormatting>')))) == (
        "invalid-x14-cf-content", "xl/worksheets/first.xml", "cfRule", "text" if ">text<" in rule else "tail",
    )


def test_rule_owned_whitespace_mixed_content_is_allowed(tmp_path):
    rule = '<x14:cfRule> \t\n <xm:f/> \r <x14:dxf/> \n </x14:cfRule>'
    result = read_worksheet_x14_cf_owner_topology(package(
        tmp_path / "rule-whitespace.xlsx",
        sheet_one=worksheet(ext(f'<x14:conditionalFormatting>{rule}</x14:conditionalFormatting>')),
    ))
    assert len(result.worksheets[0].containers) == 1


def test_rule_mixed_content_preserves_tier_and_document_precedence(tmp_path):
    later_rule_tail = ext('<x14:conditionalFormatting><x14:cfRule><xm:f/>tail</x14:cfRule></x14:conditionalFormatting>')
    assert error(package(tmp_path / "tier-one-first.xlsx", sheet_one=worksheet('<x14:cfRule/>' + later_rule_tail))) == (
        "invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", f"{{{X14}}}cfRule",
    )
    earlier_unknown_child = ext('<x14:conditionalFormatting><bad/><x14:cfRule><xm:f/>tail</x14:cfRule></x14:conditionalFormatting>')
    assert error(package(tmp_path / "unknown-child-first.xlsx", sheet_one=worksheet(earlier_unknown_child))) == (
        "unknown-x14-cf-child", "xl/worksheets/first.xml", "tag", f"{{http://schemas.openxmlformats.org/spreadsheetml/2006/main}}bad",
    )


def test_dfs_entry_and_owner_exit_precedence(tmp_path):
    # The first fault is selected by real DFS event timing, within a tier.
    root_rule_then_duplicate = '<x14:cfRule/>' + ext('<x14:conditionalFormatting/>') + ext('<x14:conditionalFormatting/>')
    assert error(package(tmp_path / "rule-first.xlsx", sheet_one=worksheet(root_rule_then_duplicate))) == (
        "invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", f"{{{X14}}}cfRule",
    )
    bad_child_then_tail = f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting><bad/></x14:conditionalFormatting>tail</x14:conditionalFormattings></ext></extLst>'
    assert error(package(tmp_path / "child-first.xlsx", sheet_one=worksheet(bad_child_then_tail))) == (
        "unknown-x14-cf-child", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}bad",
    )
    misplaced_then_missing = '<x14:cfRule/>' + f'<extLst><ext uri="{CF_URI}"/></extLst>'
    assert error(package(tmp_path / "placement-first.xlsx", sheet_one=worksheet(misplaced_then_missing))) == (
        "invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", f"{{{X14}}}cfRule",
    )


class _CountedPathLike:
    def __init__(self, result): self.result = result; self.calls = 0
    def __fspath__(self): self.calls += 1; return self.result


def test_pathlike_is_coerced_once_for_success_non_string_and_topology_failure(monkeypatch, tmp_path):
    success = _CountedPathLike(str(package(tmp_path / "path.xlsx")))
    assert len(read_worksheet_x14_cf_owner_topology(success).worksheets) == 2
    assert success.calls == 1
    non_string = _CountedPathLike(7)
    assert error(non_string) == ("invalid-package-path", f"{__name__}._CountedPathLike", "path", "TypeError")
    assert non_string.calls == 1
    raising = _CountedPathLike(str(tmp_path / "missing.xlsx"))
    sentinel = RuntimeError("topology")
    monkeypatch.setattr(owner_topology, "read_workbook_topology", lambda path: (_ for _ in ()).throw(sentinel))
    with pytest.raises(RuntimeError) as captured: read_worksheet_x14_cf_owner_topology(raising)
    assert captured.value is sentinel and raising.calls == 1


@pytest.mark.parametrize(("payload", "expected"), [
    (b" ", ("malformed-worksheet-xml", "xml", "xml")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">', ("malformed-worksheet-xml", "xml", "xml")),
    (b'<?xml version="1.0" encoding="definitely-not-an-encoding"?><worksheet/>', ("unsupported-xml-encoding", "xml", "encoding")),
    (b"<notWorksheet/>", ("invalid-worksheet-root", "root", "notWorksheet")),
])
def test_xml_encoding_and_root_boundaries(tmp_path, payload, expected):
    assert error(package(tmp_path / "xml.xlsx", sheet_one=payload)) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


def test_one_worksheet_xml_parse_per_topology_worksheet(monkeypatch, tmp_path):
    original = owner_topology.ET.fromstring; calls = []
    def counted(payload): calls.append(payload); return original(payload)
    monkeypatch.setattr(owner_topology.ET, "fromstring", counted)
    read_worksheet_x14_cf_owner_topology(package(tmp_path / "count.xlsx"))
    assert sum(payload.startswith(b"<worksheet") for payload in calls) == 2


class _RaisingPathLike:
    def __init__(self, exception): self.exception = exception; self.calls = 0
    def __fspath__(self): self.calls += 1; raise self.exception


@pytest.mark.parametrize(("value", "expected"), [
    (_RaisingPathLike(TypeError("type")), ("invalid-package-path", "path", "TypeError")),
    (_RaisingPathLike(ValueError("value")), ("unreadable-package", "path", "ValueError")),
    (_RaisingPathLike(OSError("os")), ("unreadable-package", "path", "OSError")),
    ("bad\0path", ("unreadable-package", "path", "embedded-nul")),
])
def test_path_boundaries_are_exact_and_coerced_once(value, expected):
    assert error(value) == (expected[0], "bad\0path" if expected[2] == "embedded-nul" else f"{__name__}.{type(value).__qualname__}", expected[1], expected[2])
    if hasattr(value, "calls"):
        assert value.calls == 1


def test_non_string_fspath_result_is_an_exact_typed_failure(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(owner_topology, "os", SimpleNamespace(fspath=lambda value: 7))
    assert error(sentinel) == ("invalid-package-path", "builtins.object", "path", "int")


def _member_archive(destination: Path, names: tuple[str, ...], *, payload: bytes | None = None) -> Path:
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name in names:
            info = ZipInfo(name); info.compress_type = ZIP_DEFLATED
            archive.writestr(info, payload or worksheet())
    return destination


def _one_sheet_topology(monkeypatch):
    descriptor = WorksheetDescriptor("Only", 1, "visible", "only", CanonicalPartURI("xl/worksheets/first.xml"))
    monkeypatch.setattr(owner_topology, "read_workbook_topology", lambda _: SimpleNamespace(worksheets=(descriptor,)))


@pytest.mark.parametrize(("names", "expected"), [
    ((), ("missing-worksheet-member", "member", "xl/worksheets/first.xml")),
    (("XL/WORKSHEETS/FIRST.XML",), ("noncanonical-worksheet-member", "member", "XL/WORKSHEETS/FIRST.XML")),
    (("xl/worksheets/./first.xml",), ("noncanonical-worksheet-member", "member", "xl/worksheets/./first.xml")),
    (("xl/worksheets/%66irst.xml",), ("noncanonical-worksheet-member", "member", "xl/worksheets/%66irst.xml")),
    (("xl/worksheets/first.xml", "XL/WORKSHEETS/FIRST.XML"), ("ambiguous-worksheet-member", "member", "xl/worksheets/first.xml")),
    (("xl/worksheets/first.xml", "xl/worksheets/./first.xml"), ("ambiguous-worksheet-member", "member", "xl/worksheets/first.xml")),
])
def test_worksheet_member_alias_matrix(monkeypatch, tmp_path, names, expected):
    _one_sheet_topology(monkeypatch)
    assert error(_member_archive(tmp_path / "members.xlsx", names)) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


def test_worksheet_member_read_and_decompression_failures_are_exact(monkeypatch, tmp_path):
    _one_sheet_topology(monkeypatch)
    archive = _member_archive(tmp_path / "member.xlsx", ("xl/worksheets/first.xml",))
    original = owner_topology.ZipFile.read
    monkeypatch.setattr(owner_topology.ZipFile, "read", lambda self, member: (_ for _ in ()).throw(OSError("read")))
    assert error(archive) == ("unreadable-worksheet-part", "xl/worksheets/first.xml", "xml", "OSError")
    monkeypatch.setattr(owner_topology.ZipFile, "read", lambda self, member: (_ for _ in ()).throw(owner_topology.zlib.error("zlib")))
    assert error(archive) == ("unreadable-worksheet-part", "xl/worksheets/first.xml", "xml", "error")
    monkeypatch.setattr(owner_topology.ZipFile, "read", original)


@pytest.mark.parametrize(("payload", "expected"), [
    (b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>', None),
    ('<?xml version="1.0" encoding="UTF-16"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'.encode("utf-16"), None),
    (b'<?xml version="1.0" encoding="no-such-encoding"?><worksheet/>', ("unsupported-xml-encoding", "xml", "encoding")),
    (b'<x:worksheet/>', ("malformed-worksheet-xml", "xml", "xml")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" a="1" a="2"/>', ("malformed-worksheet-xml", "xml", "xml")),
])
def test_xml_byte_encoding_and_parser_boundaries(monkeypatch, tmp_path, payload, expected):
    _one_sheet_topology(monkeypatch)
    target = _member_archive(tmp_path / "bytes.xlsx", ("xl/worksheets/first.xml",), payload=payload)
    if expected is None:
        assert read_worksheet_x14_cf_owner_topology(target).worksheets[0].containers == ()
    else:
        assert error(target) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


@pytest.mark.parametrize("local", ("conditionalFormattings", "conditionalFormatting", "cfRule", "dxf", "f", "sqref"))
@pytest.mark.parametrize("body", (
    "<{local}/>",
    "<extLst><{local}/></extLst>",
    "<extLst><ext uri=\"wrong\"><{local}/></ext></extLst>",
    "<outer><extLst><ext uri=\"wrong\"><{local}/></ext></extLst></outer>",
))
def test_all_owned_locals_are_rejected_at_every_nonowner_depth(tmp_path, local, body):
    tag = f"{{{X14 if local not in {'f', 'sqref'} else 'http://schemas.microsoft.com/office/excel/2006/main'}}}{local}"
    actual = error(package(tmp_path / f"misplaced-{local}.xlsx", sheet_one=worksheet(body.format(local=f"x14:{local}" if local not in {"f", "sqref"} else f"xm:{local}"))))
    if local == "conditionalFormattings" and body.startswith("<extLst><ext uri=\"wrong\""):
        assert actual == ("unsupported-x14-cf-extension-uri", "xl/worksheets/first.xml", "uri", "wrong")
    else:
        assert actual == ("invalid-x14-cf-parent", "xl/worksheets/first.xml", "tag", tag)


@pytest.mark.parametrize("local", ("conditionalFormattings", "conditionalFormatting", "cfRule", "dxf", "f", "sqref"))
@pytest.mark.parametrize("namespace", ("urn:wrong", X14.upper()))
def test_owned_local_wrong_uri_and_case_collisions_are_exact(tmp_path, local, namespace):
    tag = f"{{{namespace}}}{local}"
    assert error(package(tmp_path / f"collision-{local}.xlsx", sheet_one=worksheet(f'<x:{local} xmlns:x="{namespace}"/>'))) == (
        "x14-cf-namespace-collision", "xl/worksheets/first.xml", "tag", tag,
    )


@pytest.mark.parametrize(("body", "tag"), (
    ('<foreign:conditionalFormatting xmlns:foreign="urn:foreign"/>', "{urn:foreign}conditionalFormatting"),
    ('<foreign:cfRule xmlns:foreign="urn:foreign"/>', "{urn:foreign}cfRule"),
    ('<conditionalFormatting xmlns=""/>', "conditionalFormatting"),
    ('<cfRule xmlns=""/>', "cfRule"),
))
def test_foreign_and_empty_owned_local_collisions_are_exact(tmp_path, body, tag):
    assert error(package(tmp_path / "foreign.xlsx", sheet_one=worksheet(body))) == (
        "x14-cf-namespace-collision", "xl/worksheets/first.xml", "tag", tag,
    )


@pytest.mark.parametrize(("body", "field", "detail"), [
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/></x14:conditionalFormattings>tail</ext></extLst>', "ext", "tail"),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting/>tail<x14:conditionalFormatting/>later</x14:conditionalFormattings></ext></extLst>', "conditionalFormattings", "tail"),
    (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings><x14:conditionalFormatting>text</x14:conditionalFormatting></x14:conditionalFormattings></ext></extLst>', "conditionalFormatting", "text"),
])
def test_ext_and_container_mixed_content_exact_tuples(tmp_path, body, field, detail):
    assert error(package(tmp_path / "tails.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-content", "xl/worksheets/first.xml", field, detail,
    )
