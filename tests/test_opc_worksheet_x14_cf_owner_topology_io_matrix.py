"""I/O boundary matrix for the frozen X14 CF owner-topology reader."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

import rns_import_server.opc_worksheet_x14_cf_owner_topology as reader
from rns_import_server.opc_part_uri import CanonicalPartURI
from rns_import_server.opc_workbook_topology import WorkbookTopology, WorksheetDescriptor
from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError,
    read_worksheet_x14_cf_owner_topology,
)


SML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
FIRST = CanonicalPartURI("xl/worksheets/first.xml")
SECOND = CanonicalPartURI("xl/worksheets/second.xml")
_TIME = (1980, 1, 1, 0, 0, 0)


def worksheet(body: str = "") -> bytes:
    return f'<worksheet xmlns="{SML}">{body}</worksheet>'.encode()


def package(destination: Path, members: tuple[tuple[str, bytes | None], ...]) -> Path:
    """Write raw members; unlike shared fixtures, None and b'' stay distinct."""
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in members:
            if payload is None:
                continue
            info = ZipInfo(name, date_time=_TIME)
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, payload)
    return destination


def topology(*parts: CanonicalPartURI) -> WorkbookTopology:
    descriptors = tuple(
        WorksheetDescriptor(f"Sheet {index}", index, "visible", f"r{index}", part)
        for index, part in enumerate(parts, 1)
    )
    return WorkbookTopology(CanonicalPartURI("xl/workbook.xml"), descriptors)


def isolate(monkeypatch, *parts: CanonicalPartURI) -> WorkbookTopology:
    value = topology(*parts)
    monkeypatch.setattr(reader, "read_workbook_topology", lambda path: value)
    return value


def error(path) -> tuple[str, str, str, str]:
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_owner_topology(path)
    return captured.value.as_tuple()


class _PathLike:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def __fspath__(self):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def test_path_input_matrix_is_exact_and_coerced_once(monkeypatch, tmp_path):
    expected = isolate(monkeypatch, FIRST)
    success = _PathLike(str(package(tmp_path / "ok.xlsx", ((FIRST.value, worksheet()),))))
    result = read_worksheet_x14_cf_owner_topology(success)
    assert result.worksheets[0].worksheet is expected.worksheets[0]
    assert success.calls == 1
    cases = (
        (_PathLike(TypeError("bad")), ("invalid-package-path", f"{__name__}._PathLike", "path", "TypeError")),
        (_PathLike(ValueError("bad")), ("unreadable-package", f"{__name__}._PathLike", "path", "ValueError")),
        (_PathLike(OSError("bad")), ("unreadable-package", f"{__name__}._PathLike", "path", "OSError")),
        (_PathLike(b"not-a-path"), ("invalid-package-path", f"{__name__}._PathLike", "path", "bytes")),
        (_PathLike("bad\0path"), ("unreadable-package", "bad\0path", "path", "embedded-nul")),
    )
    for value, expected in cases:
        assert error(value) == expected
        assert value.calls == 1


def test_topology_identity_descriptor_equality_and_canonical_selection(monkeypatch, tmp_path):
    expected = isolate(monkeypatch, FIRST)
    result = read_worksheet_x14_cf_owner_topology(package(tmp_path / "canonical.xlsx", ((FIRST.value, worksheet()),)))
    assert result.worksheets[0].worksheet is expected.worksheets[0]
    assert result.worksheets[0].worksheet == expected.worksheets[0]


@pytest.mark.parametrize(("members", "expected"), [
    ((), ("missing-worksheet-member", FIRST.value, "member", FIRST.value)),
    ((("xl/worksheets/First.xml", worksheet()),), ("noncanonical-worksheet-member", FIRST.value, "member", "xl/worksheets/First.xml")),
    ((("xl/worksheets/./first.xml", worksheet()),), ("noncanonical-worksheet-member", FIRST.value, "member", "xl/worksheets/./first.xml")),
    ((("xl/worksheets/%66irst.xml", worksheet()),), ("noncanonical-worksheet-member", FIRST.value, "member", "xl/worksheets/%66irst.xml")),
    (((FIRST.value, worksheet()), ("xl/worksheets/%66irst.xml", worksheet())), ("ambiguous-worksheet-member", FIRST.value, "member", FIRST.value)),
    ((("xl/worksheets/First.xml", worksheet()), ("xl/worksheets/./first.xml", worksheet())), ("ambiguous-worksheet-member", FIRST.value, "member", FIRST.value)),
])
def test_member_alias_matrix_is_exact(monkeypatch, tmp_path, members, expected):
    isolate(monkeypatch, FIRST)
    assert error(package(tmp_path / "members.xlsx", members)) == expected


def test_invalid_member_and_decompression_failures_are_exact(monkeypatch, tmp_path):
    isolate(monkeypatch, FIRST)
    assert error(package(tmp_path / "invalid-member.xlsx", (("../invalid.xml", worksheet()),))) == (
        "unreadable-worksheet-part", FIRST.value, "member", "invalid-member-name",
    )
    path = package(tmp_path / "corrupt.xlsx", ((FIRST.value, worksheet("<ext>" + "a" * 10_000 + "</ext>")),))
    with ZipFile(path) as archive:
        info = archive.getinfo(FIRST.value)
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    damaged = bytearray(path.read_bytes())
    damaged[offset] ^= 0xFF
    path.write_bytes(damaged)
    assert error(path) == ("unreadable-worksheet-part", FIRST.value, "xml", "error")


@pytest.mark.parametrize(("payload", "expected"), [
    (b"", ("malformed-worksheet-xml", FIRST.value, "xml", "xml")),
    (b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>', None),
    ('<?xml version="1.0" encoding="UTF-16"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'.encode("utf-16"), None),
    (b'<?xml version="1.0" encoding="definitely-not-an-encoding"?><worksheet/>', ("unsupported-xml-encoding", FIRST.value, "xml", "encoding")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><x14:conditionalFormatting/></worksheet>', ("malformed-worksheet-xml", FIRST.value, "xml", "xml")),
    (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:a="urn:same" xmlns:b="urn:same" a:value="1" b:value="2"/>', ("malformed-worksheet-xml", FIRST.value, "xml", "xml")),
])
def test_xml_boundary_matrix_preserves_empty_bytes_and_expanded_qname(monkeypatch, tmp_path, payload, expected):
    isolate(monkeypatch, FIRST)
    path = package(tmp_path / "xml.xlsx", ((FIRST.value, payload),))
    if expected is None:
        assert read_worksheet_x14_cf_owner_topology(path).worksheets[0].containers == ()
    else:
        assert error(path) == expected


def test_none_member_is_missing_while_empty_bytes_is_malformed(monkeypatch, tmp_path):
    isolate(monkeypatch, FIRST)
    assert error(package(tmp_path / "none.xlsx", ((FIRST.value, None),))) == (
        "missing-worksheet-member", FIRST.value, "member", FIRST.value,
    )
    assert error(package(tmp_path / "empty.xlsx", ((FIRST.value, b""),))) == (
        "malformed-worksheet-xml", FIRST.value, "xml", "xml",
    )


def test_each_worksheet_is_parsed_once(monkeypatch, tmp_path):
    expected = isolate(monkeypatch, FIRST, SECOND)
    original = reader.ET.fromstring
    calls = []

    def counted(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(reader.ET, "fromstring", counted)
    result = read_worksheet_x14_cf_owner_topology(package(
        tmp_path / "parse-count.xlsx", ((FIRST.value, worksheet()), (SECOND.value, worksheet())),
    ))
    assert tuple(item.worksheet for item in result.worksheets) == expected.worksheets
    assert calls == [worksheet(), worksheet()]
