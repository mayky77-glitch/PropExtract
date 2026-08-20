from __future__ import annotations

from dataclasses import FrozenInstanceError
from zipfile import ZipFile

import pytest

import rns_import_server.opc_worksheet_native_cf_reader as reader
from rns_import_server.opc_part_uri import CanonicalPartURI
from rns_import_server.opc_workbook_topology import WorkbookTopology, WorksheetDescriptor
from rns_import_server.opc_worksheet_native_cf_reader import (
    OPCWorksheetNativeCfReaderError,
    WorkbookNativeCfPresence,
    WorksheetNativeCfPresence,
    read_worksheet_native_cf_presence,
)
from tests.opc_worksheet_native_cf_fixture_factory import package, worksheet


PART = CanonicalPartURI("xl/worksheets/first.xml")


def error(path):
    with pytest.raises(OPCWorksheetNativeCfReaderError) as captured:
        read_worksheet_native_cf_presence(path)
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
    ("xl/worksheets/First.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/First.xml")),
    ("xl/worksheets/./first.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/./first.xml")),
    ("xl/worksheets/first.xml", (("xl/worksheets/%66irst.xml", worksheet()),), ("ambiguous-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
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
