from __future__ import annotations

from dataclasses import FrozenInstanceError
from zipfile import ZipFile

import pytest

import rns_import_server.opc_worksheet_native_cf_reader as reader
from rns_import_server.opc_part_uri import CanonicalPartURI
from rns_import_server.opc_workbook_topology import WorkbookTopology, WorksheetDescriptor
from rns_import_server.opc_worksheet_native_cf_reader import (
    NativeCfA1Range,
    NativeCfContainerInventory,
    NativeCfRuleCore,
    NativeCfRuleCoreContainer,
    OPCWorksheetNativeCfReaderError,
    WorkbookNativeCfContainerInventory,
    WorkbookNativeCfPresence,
    WorkbookNativeCfRuleCoreSemantics,
    WorksheetNativeCfContainerInventory,
    WorksheetNativeCfPresence,
    WorksheetNativeCfRuleCoreSemantics,
    read_worksheet_native_cf_container_inventory,
    read_worksheet_native_cf_presence,
    read_worksheet_native_cf_rule_core_semantics,
)
from tests.opc_worksheet_native_cf_fixture_factory import package, worksheet


PART = CanonicalPartURI("xl/worksheets/first.xml")


def error(path):
    with pytest.raises(OPCWorksheetNativeCfReaderError) as captured:
        read_worksheet_native_cf_presence(path)
    return captured.value.as_tuple()


def inventory_error(path):
    with pytest.raises(OPCWorksheetNativeCfReaderError) as captured:
        read_worksheet_native_cf_container_inventory(path)
    return captured.value.as_tuple()


def rule_core_error(path):
    with pytest.raises(OPCWorksheetNativeCfReaderError) as captured:
        read_worksheet_native_cf_rule_core_semantics(path)
    return captured.value.as_tuple()


def isolated_topology(monkeypatch, part=PART):
    topology = WorkbookTopology(
        CanonicalPartURI("xl/workbook.xml"),
        (WorksheetDescriptor("First", 1, "visible", "one", part),),
    )
    monkeypatch.setattr(reader, "read_workbook_topology", lambda path: topology)


def test_full_projection_order_and_immutable_records(tmp_path):
    opaque_source = (
        '<sheetData><row r="6"/><row r="10"/><row r="104"/></sheetData>'
        '<conditionalFormatting sqref="not-owned"><cfRule type="expression" priority="0" dxfId="bad">'
        '<formula>also-not-owned</formula></cfRule></conditionalFormatting>'
    )
    result = read_worksheet_native_cf_presence(package(tmp_path / "projection.xlsx", sheet_one=worksheet(opaque_source)))
    first = WorksheetDescriptor("Первый", 1, "visible", "one", CanonicalPartURI("xl/worksheets/first.xml"))
    second = WorksheetDescriptor("Второй", 2, "visible", "two", CanonicalPartURI("xl/worksheets/второй.xml"))
    assert result == WorkbookNativeCfPresence((
        WorksheetNativeCfPresence(first, True),
        WorksheetNativeCfPresence(second, False),
    ))
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].has_native_conditional_formatting = False
    with pytest.raises(FrozenInstanceError):
        result.worksheets = ()


@pytest.mark.parametrize(("body", "expected"), [
    ("", False),
    ("<conditionalFormatting/>", True),
    ("<conditionalFormatting/><conditionalFormatting/>", True),
    ("<conditionalFormatting><cfRule/></conditionalFormatting>", True),
])
def test_presence_counts_only_legal_direct_native_containers(tmp_path, body, expected):
    result = read_worksheet_native_cf_presence(package(tmp_path / "presence.xlsx", sheet_one=worksheet(body)))
    assert result.worksheets[0] == WorksheetNativeCfPresence(
        WorksheetDescriptor("Первый", 1, "visible", "one", PART), expected,
    )


def test_topology_exception_identity_and_normalized_path_precede_zip_read(monkeypatch, tmp_path):
    sentinel = RuntimeError("topology sentinel")
    observed = []

    def fail(path):
        observed.append(path)
        raise sentinel

    monkeypatch.setattr(reader, "read_workbook_topology", fail)
    with pytest.raises(RuntimeError) as captured:
        read_worksheet_native_cf_presence(tmp_path / "not-opened.xlsx")
    assert captured.value is sentinel
    assert observed == [str(tmp_path / "not-opened.xlsx")]


class _PathLike:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def __fspath__(self):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.mark.parametrize(("outcome", "code", "detail"), [
    (TypeError("bad"), "invalid-package-path", "TypeError"),
    (ValueError("bad"), "unreadable-package", "ValueError"),
    (OSError("bad"), "unreadable-package", "OSError"),
    (Exception("bad"), "unreadable-package", "Exception"),
    (b"not-a-path", "invalid-package-path", "bytes"),
])
def test_pathlike_failures_are_typed_and_called_once(outcome, code, detail):
    value = _PathLike(outcome)
    assert error(value) == (code, f"{_PathLike.__module__}.{_PathLike.__qualname__}", "path", detail)
    assert value.calls == 1


def test_direct_bytes_and_nul_path_are_typed_before_topology():
    assert error(b"not-a-package-path") == ("invalid-package-path", "builtins.bytes", "path", "bytes")
    value = _PathLike("bad\x00path")
    assert error(value) == ("unreadable-package", "bad\x00path", "path", "embedded-nul")
    assert value.calls == 1


@pytest.mark.parametrize(("member_name", "extra_members", "expected"), [
    ("xl/worksheets/missing.xml", (), ("missing-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/%66irst.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/%66irst.xml")),
    ("xl/worksheets/%46irst.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/%46irst.xml")),
    ("xl/worksheets/%66IRST.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/%66IRST.xml")),
    ("xl/worksheets/First.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/First.xml")),
    ("xl/worksheets/./first.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/./first.xml")),
    ("xl/worksheets/first.xml", (("xl/worksheets/%66irst.xml", worksheet()),), ("ambiguous-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/first.xml", (("xl/worksheets/%46irst.xml", worksheet()),), ("ambiguous-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/first.xml", (("xl/worksheets/%66IRST.xml", worksheet()),), ("ambiguous-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/first.xml", (("xl/worksheets/First.xml", worksheet()),), ("ambiguous-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/first.xml", (("xl/worksheets/./first.xml", worksheet()),), ("ambiguous-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/first.xml", (("../invalid.xml", worksheet()),), ("unreadable-worksheet-part", "xl/worksheets/first.xml", "member", "invalid-member-name")),
])
def test_raw_member_boundary_is_strict(monkeypatch, tmp_path, member_name, extra_members, expected):
    isolated_topology(monkeypatch)
    path = package(tmp_path / "raw-member.xlsx", sheet_one_name=member_name, extra_members=extra_members)
    assert error(path) == expected


def test_bad_zip_is_typed(monkeypatch, tmp_path):
    isolated_topology(monkeypatch)
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip")
    assert error(path) == ("unreadable-worksheet-part", "xl/worksheets/first.xml", "xml", "BadZipFile")


def test_empty_native_zip_is_missing_topology_owned_member(monkeypatch, tmp_path):
    isolated_topology(monkeypatch)
    path = tmp_path / "empty.zip"
    with ZipFile(path, "w"):
        pass
    assert error(path) == ("missing-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")


def test_zlib_decompression_failure_is_typed(monkeypatch, tmp_path):
    isolated_topology(monkeypatch)
    path = package(tmp_path / "corrupt.xlsx", sheet_one=worksheet("<ext>" + "a" * 10_000 + "</ext>"))
    with ZipFile(path) as archive:
        info = archive.getinfo("xl/worksheets/first.xml")
        payload_start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    contents = bytearray(path.read_bytes())
    contents[payload_start] ^= 0xFF
    path.write_bytes(contents)
    assert error(path) == ("unreadable-worksheet-part", "xl/worksheets/first.xml", "xml", "error")


@pytest.mark.parametrize(("payload", "expected"), [
    (b"", ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<?xml version="1.0" encoding="UTF-8"<worksheet/>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-16"?><worksheet/>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<?xml version="1.0" encoding="unknown-encoding"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (b'<?xml version="1.0" encoding="UTF-7"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (b'<?xml version="1.0" encoding="UTF-32"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (b'<?xml version="1.0" encoding="EBCDIC-CP-US"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (b'<?xml version="1.0" encoding="UTF-16LE"?><worksheet/>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b"<notWorksheet/>", ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "notWorksheet")),
])
def test_xml_boundaries_are_typed(tmp_path, payload, expected):
    assert error(package(tmp_path / "xml.xlsx", sheet_one=payload)) == expected


def test_utf16_bom_is_supported(tmp_path):
    payload = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'.encode("utf-16")
    assert read_worksheet_native_cf_presence(package(tmp_path / "utf16.xlsx", sheet_one=payload)).worksheets[0].has_native_conditional_formatting is False


@pytest.mark.parametrize(("body", "expected"), [
    ("<cfRule/>", ("invalid-owned-native-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}cfRule")),
    ("<ext><conditionalFormatting/></ext>", ("invalid-owned-native-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}conditionalFormatting")),
    ("<ext><cfRule/></ext>", ("invalid-owned-native-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}cfRule")),
    ("<conditionalFormatting><conditionalFormatting/></conditionalFormatting>", ("invalid-owned-native-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}conditionalFormatting")),
    ("<conditionalFormatting><cfRule><cfRule/></cfRule></conditionalFormatting>", ("invalid-owned-native-cf-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}cfRule")),
])
def test_native_tags_are_valid_only_at_owned_depth(tmp_path, body, expected):
    assert error(package(tmp_path / "depth.xlsx", sheet_one=worksheet(body))) == expected


@pytest.mark.parametrize(("body", "tag"), [
    ('<x:conditionalFormatting xmlns:x="urn:foreign"/>', "{urn:foreign}conditionalFormatting"),
    ('<conditionalFormatting><x:cfRule xmlns:x="urn:foreign"/></conditionalFormatting>', "{urn:foreign}cfRule"),
    ('<conditionalFormatting xmlns=""/>', "conditionalFormatting"),
    ('<conditionalFormatting><cfRule xmlns=""/></conditionalFormatting>', "cfRule"),
])
def test_foreign_or_empty_namespace_owned_lookalikes_fail_closed(tmp_path, body, tag):
    assert error(package(tmp_path / "collision.xlsx", sheet_one=worksheet(body))) == (
        "owned-native-cf-namespace-collision", "xl/worksheets/first.xml", "tag", tag,
    )


def test_foreign_lookalikes_outside_owned_positions_are_not_claimed(tmp_path):
    body = '<ext xmlns="urn:foreign"><conditionalFormatting><cfRule/></conditionalFormatting></ext>'
    assert read_worksheet_native_cf_presence(package(tmp_path / "foreign.xlsx", sheet_one=worksheet(body))).worksheets[0].has_native_conditional_formatting is False


def test_unrelated_extension_coexists_with_native_cf_absence(tmp_path):
    body = '<extLst><ext uri="urn:unrelated"><payload/></ext></extLst>'
    assert read_worksheet_native_cf_presence(package(tmp_path / "extension.xlsx", sheet_one=worksheet(body))).worksheets[0].has_native_conditional_formatting is False


@pytest.mark.parametrize(("body", "local"), [
    ("<x14:conditionalFormattings/>", "conditionalFormattings"),
    ("<x14:conditionalFormatting/>", "conditionalFormatting"),
    ("<x14:cfRule/>", "cfRule"),
    ("<conditionalFormatting><x14:conditionalFormatting/></conditionalFormatting>", "conditionalFormatting"),
    ("<conditionalFormatting><cfRule><extLst><ext><x14:cfRule/></ext></extLst></cfRule></conditionalFormatting>", "cfRule"),
    ("<ext xmlns=\"urn:foreign\"><deep><x14:conditionalFormatting/></deep></ext>", "conditionalFormatting"),
])
def test_x14_cf_at_any_depth_is_hard_stop(tmp_path, body, local):
    assert error(package(tmp_path / "x14.xlsx", sheet_one=worksheet(body))) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag",
        "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}" + local,
    )


def test_x14_precedes_native_success_or_native_structure_failure(tmp_path):
    body = '<cfRule/><conditionalFormatting><x14:cfRule/></conditionalFormatting>'
    assert error(package(tmp_path / "x14-first.xlsx", sheet_one=worksheet(body))) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag",
        "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}cfRule",
    )


@pytest.mark.parametrize(("body", "field", "detail"), [
    ("<conditionalFormatting>text</conditionalFormatting>", "conditionalFormatting", "text"),
    ("<conditionalFormatting><cfRule/>tail</conditionalFormatting>", "conditionalFormatting", "tail"),
    ("<conditionalFormatting><cfRule>text</cfRule></conditionalFormatting>", "cfRule", "text"),
    ("<conditionalFormatting><cfRule><formula/>tail</cfRule></conditionalFormatting>", "cfRule", "tail"),
])
def test_owned_mixed_content_is_typed(tmp_path, body, field, detail):
    assert error(package(tmp_path / "mixed.xlsx", sheet_one=worksheet(body))) == (
        "invalid-native-cf-content", "xl/worksheets/first.xml", field, detail,
    )


def test_container_inventory_projects_ordered_two_sheet_geometry_and_is_immutable(tmp_path):
    first_payload = worksheet(
        '<conditionalFormatting sqref="$a$6 B10:C10" pivot="true" '
        'xr:uid="{01234567-89ab-cdef-0123-456789abcdef}"><cfRule/><cfRule/></conditionalFormatting>'
        '<conditionalFormatting sqref="D104"/>'
        '<conditionalFormatting sqref="XFD1048576" pivot="0"/>'
    )
    result = read_worksheet_native_cf_container_inventory(
        package(tmp_path / "inventory.xlsx", sheet_one=first_payload),
    )
    first = WorksheetDescriptor("Первый", 1, "visible", "one", PART)
    second = WorksheetDescriptor("Второй", 2, "visible", "two", CanonicalPartURI("xl/worksheets/второй.xml"))
    first_container = NativeCfContainerInventory(
        "xl/worksheets/first.xml/worksheet/conditionalFormatting[1]",
        (
            NativeCfA1Range("A6", "A6", 6, 1, 6, 1),
            NativeCfA1Range("B10", "C10", 10, 2, 10, 3),
        ),
        True,
        "{01234567-89ab-cdef-0123-456789abcdef}",
        2,
    )
    assert result == WorkbookNativeCfContainerInventory((
        WorksheetNativeCfContainerInventory(first, (
            first_container,
            NativeCfContainerInventory(
                "xl/worksheets/first.xml/worksheet/conditionalFormatting[2]",
                (NativeCfA1Range("D104", "D104", 104, 4, 104, 4),),
                None,
                None,
                0,
            ),
            NativeCfContainerInventory(
                "xl/worksheets/first.xml/worksheet/conditionalFormatting[3]",
                (NativeCfA1Range("XFD1048576", "XFD1048576", 1_048_576, 16_384, 1_048_576, 16_384),),
                False,
                None,
                0,
            ),
        )),
        WorksheetNativeCfContainerInventory(second, ()),
    ))
    with pytest.raises(FrozenInstanceError):
        result.worksheets = ()
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers = ()
    with pytest.raises(FrozenInstanceError):
        first_container.sqref[0].min_row = 1
    with pytest.raises(FrozenInstanceError):
        first_container.rule_count = 0


def test_container_inventory_record_field_order_is_frozen():
    assert tuple(NativeCfA1Range.__dataclass_fields__) == (
        "start_coordinate", "end_coordinate", "min_row", "min_column", "max_row", "max_column",
    )
    assert tuple(NativeCfContainerInventory.__dataclass_fields__) == (
        "owner_path", "sqref", "pivot", "uid", "rule_count",
    )
    assert tuple(WorksheetNativeCfContainerInventory.__dataclass_fields__) == ("worksheet", "containers")
    assert tuple(WorkbookNativeCfContainerInventory.__dataclass_fields__) == ("worksheets",)


@pytest.mark.parametrize(("sqref", "expected"), [
    ("A6", None),
    ("$a$6\tB10:C10\r\nXFD104", None),
    ("A:A", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A:A")),
    ("6:6", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "6:6")),
    ("Sheet1!A6", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "Sheet1!A6")),
    ("A0", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A0")),
    ("XFE1", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "XFE1")),
    ("A1048577", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A1048577")),
    ("A0000001", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A0000001")),
    ("A12345678", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A12345678")),
    ("A6:B5", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A6:B5")),
    ("B6:A7", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B6:A7")),
    ("A6 A6", ("duplicate-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A6")),
    ("$A$6 a6", ("duplicate-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "a6")),
    ("A6:A7 A7:A8", ("overlapping-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A7:A8")),
    ("A6:B7 B7:C8", ("overlapping-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B7:C8")),
    ("A1:C3 B2", ("overlapping-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B2")),
    ("A1:C3 B2:D2", ("overlapping-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B2:D2")),
])
def test_container_inventory_sqref_geometry(tmp_path, sqref, expected):
    path = package(
        tmp_path / "sqref-inventory.xlsx",
        sheet_one=worksheet(f'<conditionalFormatting sqref="{sqref}"/>'),
    )
    if expected is None:
        ranges = read_worksheet_native_cf_container_inventory(path).worksheets[0].containers[0].sqref
        assert len(ranges) == (1 if sqref == "A6" else 3)
    else:
        assert inventory_error(path) == expected


def test_container_inventory_rejects_a_truly_overlong_sqref_token(tmp_path):
    token = "A" * 10_000 + "1"
    path = package(
        tmp_path / "overlong-sqref-inventory.xlsx",
        sheet_one=worksheet(f'<conditionalFormatting sqref="{token}"/>'),
    )
    assert inventory_error(path) == ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", token)


@pytest.mark.parametrize(("body", "expected"), [
    ('<conditionalFormatting/>', ("missing-native-cf-attribute", "xl/worksheets/first.xml", "attribute", "sqref")),
    ('<conditionalFormatting sqref=""/>', ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "")),
    ('<conditionalFormatting sqref="A6" extra="x"/>', ("unknown-native-cf-attribute", "xl/worksheets/first.xml", "attribute", "extra")),
    ('<conditionalFormatting sqref="A6" pivot="True"/>', ("invalid-native-cf-boolean", "xl/worksheets/first.xml", "pivot", "True")),
    ('<conditionalFormatting sqref="A6" xr:uid=""/>', ("invalid-native-cf-uid", "xl/worksheets/first.xml", "uid", "")),
    ('<conditionalFormatting sqref="A6" xr:uid="{not-a-guid}"/>', ("invalid-native-cf-uid", "xl/worksheets/first.xml", "uid", "{not-a-guid}")),
    ('<conditionalFormatting sqref="A6"><extLst/></conditionalFormatting>', ("invalid-native-cf-container-child", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}extLst")),
])
def test_container_inventory_attributes_and_children(tmp_path, body, expected):
    assert inventory_error(package(tmp_path / "attributes.xlsx", sheet_one=worksheet(body))) == expected


@pytest.mark.parametrize(("body", "field", "detail"), [
    ('<conditionalFormatting sqref="A6">text</conditionalFormatting>', "conditionalFormatting", "text"),
    ('<conditionalFormatting sqref="A6"><cfRule/>tail</conditionalFormatting>', "conditionalFormatting", "tail"),
    ('<conditionalFormatting sqref="A6"><cfRule>text</cfRule></conditionalFormatting>', "cfRule", "text"),
    ('<conditionalFormatting sqref="A6"><cfRule><formula/>tail</cfRule></conditionalFormatting>', "cfRule", "tail"),
])
def test_container_inventory_matches_presence_content_boundary(tmp_path, body, field, detail):
    assert inventory_error(package(tmp_path / "inventory-mixed.xlsx", sheet_one=worksheet(body))) == (
        "invalid-native-cf-content", "xl/worksheets/first.xml", field, detail,
    )


def test_container_inventory_xml_and_x14_precedence(tmp_path):
    malformed = (
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        b'xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">'
        b'<conditionalFormatting sqref="A6" sqref="B6"><x14:cfRule/></conditionalFormatting></worksheet>'
    )
    assert inventory_error(package(tmp_path / "malformed-precedes-x14.xlsx", sheet_one=malformed)) == (
        "malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml",
    )
    x14 = worksheet('<conditionalFormatting><x14:cfRule/></conditionalFormatting>')
    assert inventory_error(package(tmp_path / "x14-precedes-semantics.xlsx", sheet_one=x14)) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag",
        "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}cfRule",
    )
    non_worksheet_x14 = (
        b'<notWorksheet xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">'
        b'<x14:conditionalFormatting/></notWorksheet>'
    )
    assert inventory_error(package(tmp_path / "x14-precedes-root.xlsx", sheet_one=non_worksheet_x14)) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag",
        "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}conditionalFormatting",
    )


@pytest.mark.parametrize(("payload", "expected"), [
    (b"", ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<?xml version="1.0" encoding="UTF-8"<worksheet/>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<?xml version="1.0" encoding="unknown-encoding"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (b'<?xml version="1.0" encoding="UTF-7"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><conditionalFormatting xr:uid="{01234567-89ab-cdef-0123-456789abcdef}" sqref="A6"/></worksheet>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><conditionalFormatting sqref="A6" sqref="B6"/></worksheet>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:a="urn:duplicate" xmlns:b="urn:duplicate"><conditionalFormatting sqref="A6" a:value="1" b:value="2"/></worksheet>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
])
def test_container_inventory_xml_parser_regressions(tmp_path, payload, expected):
    assert inventory_error(package(tmp_path / "inventory-xml-regression.xlsx", sheet_one=payload)) == expected


@pytest.mark.parametrize(("filename", "payload"), [
    (
        "inventory-utf8-bom.xlsx",
        b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
    ),
    (
        "inventory-utf16.xlsx",
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'.encode("utf-16"),
    ),
    (
        "inventory-dtd.xlsx",
        b'<!DOCTYPE worksheet [<!ENTITY ignored "<x14:cfRule/>">]>'
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        b'xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"/>',
    ),
])
def test_container_inventory_bom_encoding_and_unused_dtd_text(tmp_path, filename, payload):
    expected = WorkbookNativeCfContainerInventory((
        WorksheetNativeCfContainerInventory(
            WorksheetDescriptor("Первый", 1, "visible", "one", PART),
            (),
        ),
        WorksheetNativeCfContainerInventory(
            WorksheetDescriptor("Второй", 2, "visible", "two", CanonicalPartURI("xl/worksheets/второй.xml")),
            (),
        ),
    ))
    assert read_worksheet_native_cf_container_inventory(
        package(tmp_path / filename, sheet_one=payload),
    ) == expected


@pytest.mark.parametrize("read", [
    read_worksheet_native_cf_presence,
    read_worksheet_native_cf_container_inventory,
    read_worksheet_native_cf_rule_core_semantics,
])
def test_each_public_reader_uses_one_elementtree_parse_per_worksheet(monkeypatch, tmp_path, read):
    isolated_topology(monkeypatch)
    payload = worksheet('<conditionalFormatting sqref="A6"><cfRule type="uniqueValues" priority="1"/></conditionalFormatting>')
    path = package(tmp_path / "single-parse.xlsx", sheet_one=payload)
    original = reader.ET.fromstring
    calls = []

    def counted(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(reader.ET, "fromstring", counted)
    read(path)
    assert calls == [payload]


def test_rule_core_projects_two_sheets_in_document_order_and_is_immutable(tmp_path):
    first_payload = worksheet(
        '<conditionalFormatting sqref="A6">'
        '<cfRule type="expression" priority=" \t+001\n" dxfId="-0" stopIfTrue="false">'
        '<formula>OR(A6=1,B10=2,C104=3)</formula></cfRule>'
        '<cfRule type="uniqueValues" priority="2"/></conditionalFormatting>'
        '<conditionalFormatting sqref="B10"><cfRule type="duplicateValues" priority="3" '
        'dxfId="4294967295" stopIfTrue="true"/></conditionalFormatting>'
    )
    second_payload = worksheet(
        '<conditionalFormatting sqref="C104"><cfRule type="containsBlanks" priority="1"/></conditionalFormatting>'
        '<conditionalFormatting sqref="D104"><cfRule type="notContainsBlanks" priority="2"/></conditionalFormatting>'
        '<conditionalFormatting sqref="E104"><cfRule type="containsErrors" priority="3"/></conditionalFormatting>'
        '<conditionalFormatting sqref="F104"><cfRule type="notContainsErrors" priority="4"/></conditionalFormatting>'
    )
    result = read_worksheet_native_cf_rule_core_semantics(
        package(tmp_path / "rule-core.xlsx", sheet_one=first_payload, sheet_two=second_payload),
    )
    first = WorksheetDescriptor("Первый", 1, "visible", "one", PART)
    second = WorksheetDescriptor("Второй", 2, "visible", "two", CanonicalPartURI("xl/worksheets/второй.xml"))
    def container(owner_path, coordinate, row, column, rule_count):
        return NativeCfContainerInventory(
            owner_path,
            (NativeCfA1Range(coordinate, coordinate, row, column, row, column),),
            None,
            None,
            rule_count,
        )

    first_one = container("xl/worksheets/first.xml/worksheet/conditionalFormatting[1]", "A6", 6, 1, 2)
    first_two = container("xl/worksheets/first.xml/worksheet/conditionalFormatting[2]", "B10", 10, 2, 1)
    second_one = container("xl/worksheets/второй.xml/worksheet/conditionalFormatting[1]", "C104", 104, 3, 1)
    second_two = container("xl/worksheets/второй.xml/worksheet/conditionalFormatting[2]", "D104", 104, 4, 1)
    second_three = container("xl/worksheets/второй.xml/worksheet/conditionalFormatting[3]", "E104", 104, 5, 1)
    second_four = container("xl/worksheets/второй.xml/worksheet/conditionalFormatting[4]", "F104", 104, 6, 1)
    assert result == WorkbookNativeCfRuleCoreSemantics((
        WorksheetNativeCfRuleCoreSemantics(first, (
            NativeCfRuleCoreContainer(first_one, (
                NativeCfRuleCore(
                    "xl/worksheets/first.xml/worksheet/conditionalFormatting[1]/cfRule[1]",
                    1, "expression", 1, 0, False, ("OR(A6=1,B10=2,C104=3)",),
                ),
                NativeCfRuleCore(
                    "xl/worksheets/first.xml/worksheet/conditionalFormatting[1]/cfRule[2]",
                    2, "uniqueValues", 2, None, None, (),
                ),
            )),
            NativeCfRuleCoreContainer(first_two, (
                NativeCfRuleCore(
                    "xl/worksheets/first.xml/worksheet/conditionalFormatting[2]/cfRule[1]",
                    3, "duplicateValues", 3, 4_294_967_295, True, (),
                ),
            )),
        )),
        WorksheetNativeCfRuleCoreSemantics(second, (
            NativeCfRuleCoreContainer(second_one, (NativeCfRuleCore(
                "xl/worksheets/второй.xml/worksheet/conditionalFormatting[1]/cfRule[1]",
                1, "containsBlanks", 1, None, None, (),
            ),)),
            NativeCfRuleCoreContainer(second_two, (NativeCfRuleCore(
                "xl/worksheets/второй.xml/worksheet/conditionalFormatting[2]/cfRule[1]",
                2, "notContainsBlanks", 2, None, None, (),
            ),)),
            NativeCfRuleCoreContainer(second_three, (NativeCfRuleCore(
                "xl/worksheets/второй.xml/worksheet/conditionalFormatting[3]/cfRule[1]",
                3, "containsErrors", 3, None, None, (),
            ),)),
            NativeCfRuleCoreContainer(second_four, (NativeCfRuleCore(
                "xl/worksheets/второй.xml/worksheet/conditionalFormatting[4]/cfRule[1]",
                4, "notContainsErrors", 4, None, None, (),
            ),)),
        )),
    ))
    with pytest.raises(FrozenInstanceError):
        result.worksheets = ()
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers = ()
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers[0].container = first_two
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers[0].rules[0].priority = 0


def test_rule_core_record_field_order_is_frozen():
    assert tuple(NativeCfRuleCore.__dataclass_fields__) == (
        "owner_path", "document_order", "type", "priority", "dxf_id", "stop_if_true", "formulas",
    )
    assert tuple(NativeCfRuleCoreContainer.__dataclass_fields__) == ("container", "rules")
    assert tuple(WorksheetNativeCfRuleCoreSemantics.__dataclass_fields__) == ("worksheet", "containers")
    assert tuple(WorkbookNativeCfRuleCoreSemantics.__dataclass_fields__) == ("worksheets",)


@pytest.mark.parametrize(("priority", "expected"), [
    ("+0001", None),
    (" \t+0001\n", None),
    ("", ("invalid-native-cf-priority", "priority", "")),
    ("one", ("invalid-native-cf-priority", "priority", "one")),
    ("0", ("invalid-native-cf-priority", "priority", "0")),
    ("-1", ("invalid-native-cf-priority", "priority", "-1")),
    ("2147483648", ("invalid-native-cf-priority", "priority", "2147483648")),
    ("9" * 10_000, ("invalid-native-cf-priority", "priority", "9" * 10_000)),
])
def test_rule_core_priority_lexical_matrix(tmp_path, priority, expected):
    path = package(tmp_path / "priority.xlsx", sheet_one=worksheet(
        f'<conditionalFormatting sqref="A6"><cfRule type="uniqueValues" priority="{priority}"/></conditionalFormatting>',
    ))
    if expected is None:
        assert read_worksheet_native_cf_rule_core_semantics(path).worksheets[0].containers[0].rules[0].priority == 1
    else:
        code, field, detail = expected
        assert rule_core_error(path) == (code, "xl/worksheets/first.xml", field, detail)


def test_rule_core_rejects_worksheet_global_duplicate_priority_with_raw_lexical_detail(tmp_path):
    path = package(tmp_path / "duplicate-priority.xlsx", sheet_one=worksheet(
        '<conditionalFormatting sqref="A6"><cfRule type="uniqueValues" priority="1"/></conditionalFormatting>'
        '<conditionalFormatting sqref="B10"><cfRule type="duplicateValues" priority=" +001 "/></conditionalFormatting>',
    ))
    assert rule_core_error(path) == (
        "duplicate-native-cf-priority", "xl/worksheets/first.xml", "priority", " +001 ",
    )


@pytest.mark.parametrize(("dxf_id", "expected"), [
    ("0", 0), ("+0002", 2), ("-000", 0), ("4294967295", 4_294_967_295),
    ("-1", "invalid-native-cf-dxf-id"), ("4294967296", "invalid-native-cf-dxf-id"), ("one", "invalid-native-cf-dxf-id"),
    ("9" * 10_000, "invalid-native-cf-dxf-id"),
])
def test_rule_core_dxf_uint32_matrix(tmp_path, dxf_id, expected):
    path = package(tmp_path / "dxf.xlsx", sheet_one=worksheet(
        f'<conditionalFormatting sqref="A6"><cfRule type="uniqueValues" priority="1" dxfId="{dxf_id}"/></conditionalFormatting>',
    ))
    if isinstance(expected, int):
        assert read_worksheet_native_cf_rule_core_semantics(path).worksheets[0].containers[0].rules[0].dxf_id == expected
    else:
        assert rule_core_error(path) == (expected, "xl/worksheets/first.xml", "dxfId", dxf_id)


@pytest.mark.parametrize(("value", "expected"), [
    ("0", False), ("1", True), ("false", False), ("true", True), ("False", "invalid-native-cf-boolean"),
])
def test_rule_core_stop_if_true_is_exact(tmp_path, value, expected):
    path = package(tmp_path / "stop.xlsx", sheet_one=worksheet(
        f'<conditionalFormatting sqref="A6"><cfRule type="uniqueValues" priority="1" stopIfTrue="{value}"/></conditionalFormatting>',
    ))
    if isinstance(expected, bool):
        assert read_worksheet_native_cf_rule_core_semantics(path).worksheets[0].containers[0].rules[0].stop_if_true is expected
    else:
        assert rule_core_error(path) == (expected, "xl/worksheets/first.xml", "stopIfTrue", value)


@pytest.mark.parametrize(("body", "expected"), [
    ('<cfRule priority="1"/>', ("missing-native-cf-rule-attribute", "attribute", "type")),
    ('<cfRule type="uniqueValues"/>', ("missing-native-cf-rule-attribute", "attribute", "priority")),
    ('<cfRule type="uniqueValues" priority="1" z="x" a="x"/>', ("unknown-native-cf-rule-attribute", "attribute", "a")),
    ('<cfRule type="cellIs" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "cellIs")),
    ('<cfRule type="containsText" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "containsText")),
    ('<cfRule type="notContainsText" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "notContainsText")),
    ('<cfRule type="beginsWith" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "beginsWith")),
    ('<cfRule type="endsWith" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "endsWith")),
    ('<cfRule type="top10" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "top10")),
    ('<cfRule type="aboveAverage" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "aboveAverage")),
    ('<cfRule type="timePeriod" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "timePeriod")),
    ('<cfRule type="colorScale" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "colorScale")),
    ('<cfRule type="dataBar" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "dataBar")),
    ('<cfRule type="iconSet" priority="1"/>', ("unsupported-native-cf-rule-type", "type", "iconSet")),
])
def test_rule_core_attributes_and_unsupported_types(tmp_path, body, expected):
    path = package(tmp_path / "rule-attrs.xlsx", sheet_one=worksheet(
        f'<conditionalFormatting sqref="A6">{body}</conditionalFormatting>',
    ))
    assert rule_core_error(path) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


@pytest.mark.parametrize(("body", "expected"), [
    ('<cfRule type="expression" priority="1"/>', ("invalid-native-cf-formula-cardinality", "type", "expression")),
    ('<cfRule type="expression" priority="1"><formula>A6</formula><formula>B10</formula></cfRule>', ("invalid-native-cf-formula-cardinality", "type", "expression")),
    ('<cfRule type="expression" priority="1"><formula/></cfRule>', ("invalid-native-cf-formula-content", "formula", "blank")),
    ('<cfRule type="expression" priority="1"><formula> \t\r\n </formula></cfRule>', ("invalid-native-cf-formula-content", "formula", "blank")),
    ('<cfRule type="expression" priority="1"><formula bad="x">A6</formula></cfRule>', ("invalid-native-cf-formula-attribute", "attribute", "bad")),
    ('<cfRule type="expression" priority="1"><formula><x/></formula></cfRule>', ("invalid-native-cf-formula-content", "formula", "nested")),
    ('<cfRule type="expression" priority="1"><formula>A6</formula>tail</cfRule>', ("invalid-native-cf-content", "cfRule", "tail")),
    ('<cfRule type="expression" priority="1"><x:formula>A6</x:formula></cfRule>', ("invalid-native-cf-rule-child", "tag", "{urn:foreign}formula")),
    ('<cfRule type="uniqueValues" priority="1"><formula>A6</formula></cfRule>', ("invalid-native-cf-formula-cardinality", "type", "uniqueValues")),
    ('<cfRule type="uniqueValues" priority="1"><extLst/></cfRule>', ("invalid-native-cf-rule-child", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}extLst")),
    ('<cfRule type="uniqueValues" priority="1"><colorScale/></cfRule>', ("invalid-native-cf-rule-child", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}colorScale")),
])
def test_rule_core_formula_and_payload_boundary(tmp_path, body, expected):
    path = package(tmp_path / "formula.xlsx", sheet_one=worksheet(
        f'<conditionalFormatting sqref="A6" xmlns:x="urn:foreign">{body}</conditionalFormatting>',
    ))
    assert rule_core_error(path) == (expected[0], "xl/worksheets/first.xml", expected[1], expected[2])


def test_rule_core_x14_precedes_rule_semantics(tmp_path):
    path = package(tmp_path / "x14-rule.xlsx", sheet_one=worksheet(
        '<conditionalFormatting sqref="bad"><cfRule type="cellIs" priority="0"><x14:cfRule/></cfRule></conditionalFormatting>',
    ))
    assert rule_core_error(path) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag",
        "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}cfRule",
    )
