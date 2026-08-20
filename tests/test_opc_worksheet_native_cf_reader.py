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
    OPCWorksheetNativeCfReaderError,
    WorkbookNativeCfContainerInventory,
    WorkbookNativeCfPresence,
    WorksheetNativeCfContainerInventory,
    WorksheetNativeCfPresence,
    read_worksheet_native_cf_container_inventory,
    read_worksheet_native_cf_presence,
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


def test_inventory_projects_ordered_containers_ranges_and_immutable_records(tmp_path):
    first_xml = worksheet(
        '<conditionalFormatting sqref="$A$6 B10:C10" pivot="false" '
        'xr:uid="{01234567-89ab-cdef-0123-456789abcdef}">'
        '<cfRule type="expression" priority="999"><formula>opaque</formula></cfRule>'
        '</conditionalFormatting>'
        '<conditionalFormatting sqref="XFD104" pivot="1"><cfRule/><cfRule/></conditionalFormatting>'
    )
    second_xml = worksheet('<conditionalFormatting sqref="A1:XFD1048576"/>')
    result = read_worksheet_native_cf_container_inventory(
        package(tmp_path / "projection.xlsx", sheet_one=first_xml, sheet_two=second_xml)
    )
    first = WorksheetDescriptor("Первый", 1, "visible", "one", PART)
    second = WorksheetDescriptor("Второй", 2, "visible", "two", CanonicalPartURI("xl/worksheets/второй.xml"))
    assert result == WorkbookNativeCfContainerInventory((
        WorksheetNativeCfContainerInventory(first, (
            NativeCfContainerInventory(
                "xl/worksheets/first.xml/worksheet/conditionalFormatting[1]",
                (
                    NativeCfA1Range("A6", "A6", 6, 1, 6, 1),
                    NativeCfA1Range("B10", "C10", 10, 2, 10, 3),
                ),
                False,
                "{01234567-89ab-cdef-0123-456789abcdef}",
                1,
            ),
            NativeCfContainerInventory(
                "xl/worksheets/first.xml/worksheet/conditionalFormatting[2]",
                (NativeCfA1Range("XFD104", "XFD104", 104, 16384, 104, 16384),),
                True,
                None,
                2,
            ),
        )),
        WorksheetNativeCfContainerInventory(second, (
            NativeCfContainerInventory(
                "xl/worksheets/второй.xml/worksheet/conditionalFormatting[1]",
                (NativeCfA1Range("A1", "XFD1048576", 1, 1, 1048576, 16384),),
                None,
                None,
                0,
            ),
        )),
    ))
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers[0].rule_count = 0
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers[0].sqref[0].start_coordinate = "B6"
    with pytest.raises(FrozenInstanceError):
        result.worksheets = ()
    with pytest.raises(FrozenInstanceError):
        result.worksheets[0].containers = ()


def test_inventory_absent_containers_are_empty_tuples(tmp_path):
    result = read_worksheet_native_cf_container_inventory(package(tmp_path / "absent.xlsx"))
    assert all(record.containers == () for record in result.worksheets)


@pytest.mark.parametrize(("sqref", "expected"), [
    ("A1", (NativeCfA1Range("A1", "A1", 1, 1, 1, 1),)),
    (" \tA1\r\n", (NativeCfA1Range("A1", "A1", 1, 1, 1, 1),)),
    ("$a$1 $XFD$1048576", (
        NativeCfA1Range("A1", "A1", 1, 1, 1, 1),
        NativeCfA1Range("XFD1048576", "XFD1048576", 1048576, 16384, 1048576, 16384),
    )),
])
def test_inventory_normalizes_strict_a1_endpoints(tmp_path, sqref, expected):
    result = read_worksheet_native_cf_container_inventory(
        package(tmp_path / "a1.xlsx", sheet_one=worksheet(f'<conditionalFormatting sqref="{sqref}"/>'))
    )
    assert result.worksheets[0].containers[0].sqref == expected


@pytest.mark.parametrize(("sqref", "expected"), [
    ("", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "")),
    ("   ", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "   ")),
    ("A:A", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A:A")),
    ("6:6", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "6:6")),
    ("Sheet1!A1", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "Sheet1!A1")),
    ("[Book]Sheet1!A1", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "[Book]Sheet1!A1")),
    ("A0", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A0")),
    ("XFE1", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "XFE1")),
    ("A1048577", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A1048577")),
    ("A11111111", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A11111111")),
    ("A1:B0", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A1:B0")),
    ("B2:A1", ("invalid-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B2:A1")),
    ("A1 A1", ("duplicate-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A1")),
    ("A1:A1 A1", ("duplicate-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A1")),
    ("$A$1 A1", ("duplicate-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "A1")),
    ("A1:C3 B2:B2", ("overlapping-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B2:B2")),
    ("A1:B2 B2:C3", ("overlapping-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B2:C3")),
    ("A1:C2 B1:B3", ("overlapping-native-cf-sqref", "xl/worksheets/first.xml", "sqref", "B1:B3")),
])
def test_inventory_rejects_non_a1_duplicate_and_overlapping_sqrefs(tmp_path, sqref, expected):
    xml = f'<conditionalFormatting sqref="{sqref}"/>'
    assert inventory_error(package(tmp_path / "sqref.xlsx", sheet_one=worksheet(xml))) == expected


@pytest.mark.parametrize(("attributes", "expected"), [
    ("", ("missing-native-cf-attribute", "xl/worksheets/first.xml", "attribute", "sqref")),
    (' sqref="A1" pivot="yes"', ("invalid-native-cf-boolean", "xl/worksheets/first.xml", "pivot", "yes")),
    (' sqref="A1" xr:uid="not-a-guid"', ("invalid-native-cf-uid", "xl/worksheets/first.xml", "uid", "not-a-guid")),
    (' sqref="A1" priority="1"', ("unknown-native-cf-attribute", "xl/worksheets/first.xml", "attribute", "priority")),
    (' sqref="A1" x:sqref="B2" xmlns:x="urn:foreign"', ("unknown-native-cf-attribute", "xl/worksheets/first.xml", "attribute", "{urn:foreign}sqref")),
])
def test_inventory_container_attribute_boundary(tmp_path, attributes, expected):
    assert inventory_error(package(
        tmp_path / "attributes.xlsx", sheet_one=worksheet(f"<conditionalFormatting{attributes}/>")
    )) == expected


def test_inventory_rejects_duplicate_container_attribute_before_xml_parser(tmp_path):
    payload = worksheet('<conditionalFormatting sqref="A1" sqref="B2"/>')
    assert inventory_error(package(tmp_path / "duplicate.xlsx", sheet_one=payload)) == (
        "duplicate-native-cf-attribute", "xl/worksheets/first.xml", "attribute", "sqref",
    )


def test_inventory_duplicate_expanded_attribute_name_is_typed(tmp_path):
    body = (
        '<conditionalFormatting sqref="A1" '
        'xmlns:one="http://schemas.microsoft.com/office/spreadsheetml/2014/revision" '
        'xmlns:two="http://schemas.microsoft.com/office/spreadsheetml/2014/revision" '
        'one:uid="{01234567-89ab-cdef-0123-456789abcdef}" '
        'two:uid="{fedcba98-7654-3210-fedc-ba9876543210}"/>'
    )
    assert inventory_error(package(tmp_path / "expanded-duplicate.xlsx", sheet_one=worksheet(body))) == (
        "duplicate-native-cf-attribute", "xl/worksheets/first.xml", "attribute",
        "{http://schemas.microsoft.com/office/spreadsheetml/2014/revision}uid",
    )


def test_inventory_duplicate_detection_uses_xml_events_not_unused_dtd_text(tmp_path):
    payload = (
        b'<!DOCTYPE worksheet [<!ENTITY fake \'<conditionalFormatting sqref="A1" sqref="B2"/>\'>]>'
        + worksheet('<conditionalFormatting sqref="A1"/>')
    )
    result = read_worksheet_native_cf_container_inventory(package(tmp_path / "unused-dtd.xlsx", sheet_one=payload))
    assert result.worksheets[0].containers[0].sqref == (NativeCfA1Range("A1", "A1", 1, 1, 1, 1),)


def test_inventory_xml_and_x14_precede_duplicate_attribute_semantics(tmp_path):
    utf7 = b'<?xml version="1.0" encoding="UTF-7"?><worksheet><conditionalFormatting sqref="A1" sqref="B2"/></worksheet>'
    assert inventory_error(package(tmp_path / "utf7-duplicate.xlsx", sheet_one=utf7)) == (
        "unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding",
    )
    x14 = worksheet('<x14:cfRule/><conditionalFormatting sqref="A1" sqref="B2"/>')
    assert inventory_error(package(tmp_path / "x14-duplicate.xlsx", sheet_one=x14)) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag",
        "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}cfRule",
    )


@pytest.mark.parametrize(("body", "expected"), [
    ("<conditionalFormatting sqref=\"A1\"><extLst/></conditionalFormatting>", (
        "unsupported_native_cf_extension", "xl/worksheets/first.xml", "tag",
        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}extLst",
    )),
    ("<conditionalFormatting sqref=\"A1\"><formula/></conditionalFormatting>", (
        "invalid-native-cf-container-child", "xl/worksheets/first.xml", "tag",
        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}formula",
    )),
])
def test_inventory_rejects_unowned_direct_container_children(tmp_path, body, expected):
    assert inventory_error(package(tmp_path / "children.xlsx", sheet_one=worksheet(body))) == expected


def test_inventory_preserves_x14_precedence_and_presence_pathlike_boundary(tmp_path):
    x14 = worksheet('<conditionalFormatting sqref="A1"><x14:cfRule/></conditionalFormatting>')
    assert inventory_error(package(tmp_path / "x14.xlsx", sheet_one=x14)) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag",
        "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}cfRule",
    )
    class Once:
        def __init__(self, value):
            self.value, self.calls = value, 0
        def __fspath__(self):
            self.calls += 1
            if self.calls > 1:
                raise TypeError("called twice")
            return self.value
    path = Once(str(package(tmp_path / "once.xlsx")))
    assert read_worksheet_native_cf_container_inventory(path).worksheets[0].containers == ()
    assert path.calls == 1
