from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from opc_package_v6_corpus import FIXTURES, write_fixture
from rns_import_server.opc_package_graph import CONTENT_TYPES_NAMESPACE, OPCPackageGraphError, build_opc_package_graph
from rns_import_server.opc_part_uri import CanonicalPartURI


CONTENT_TYPES = f'<Types xmlns="{CONTENT_TYPES_NAMESPACE}"/>'.encode()
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def rels(*rows: tuple[str, str, str, str]) -> bytes:
    body = "".join('<Relationship Id="%s" Type="%s" Target="%s"%s/>' % (i, t, x, "" if m == "Internal" else f' TargetMode="{m}"') for i, t, x, m in rows)
    return f'<Relationships xmlns="{REL_NS}">{body}</Relationships>'.encode()


def write_package(tmp_path: Path, members: tuple[tuple[str, bytes], ...], name: str = "package.xlsx", compression: int = ZIP_DEFLATED) -> Path:
    path = tmp_path / name
    with ZipFile(path, "w", compression=compression) as archive:
        for member, payload in members:
            archive.writestr(member, payload)
    return path


def members(*, root_target: str = "xl/workbook.xml", workbook_target: str = "worksheets/sheet1.xml") -> tuple[tuple[str, bytes], ...]:
    return (
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", rels(("root", "https://example.test/root", root_target, "Internal"))),
        ("xl/workbook.xml", b"<workbook/>"),
        ("xl/_rels/workbook.xml.rels", rels(("sheet", "https://example.test/sheet", workbook_target, "Internal"))),
        ("xl/worksheets/sheet1.xml", b"<worksheet/>"),
    )


def error(path: Path) -> tuple[str, str, str, str]:
    with pytest.raises(OPCPackageGraphError) as caught:
        build_opc_package_graph(path)
    return caught.value.as_tuple()


def test_builds_immutable_ordered_root_nested_and_root_level_source_graph(tmp_path: Path) -> None:
    package_members = members() + (("_rels/doc.xml.rels", rels(("doc", "https://example.test/doc", "doc.xml", "Internal"))), ("doc.xml", b"<doc/>"))
    graph = build_opc_package_graph(write_package(tmp_path, package_members))
    assert [part.name.value for part in graph.parts] == ["xl/workbook.xml", "xl/worksheets/sheet1.xml", "doc.xml"]
    assert [(item.relationship_part.value, item.source.value if item.source else None, item.id, item.resolved_target.value if item.resolved_target else None) for item in graph.relationships] == [
        ("_rels/.rels", None, "root", "xl/workbook.xml"),
        ("xl/_rels/workbook.xml.rels", "xl/workbook.xml", "sheet", "xl/worksheets/sheet1.xml"),
        ("_rels/doc.xml.rels", "doc.xml", "doc", "doc.xml"),
    ]
    with pytest.raises(FrozenInstanceError):
        graph.parts[0].name = CanonicalPartURI("other.xml")  # type: ignore[misc]


def test_preserves_xml_order_and_external_uri_references(tmp_path: Path) -> None:
    package_members = list(members())
    package_members[3] = ("xl/_rels/workbook.xml.rels", rels(
        ("two", "https://example.test/t", "../outside.xml", "External"),
        ("one", "https://example.test/t", "/outside.xml", "External"),
        ("three", "https://example.test/t", "//host/outside.xml", "External"),
        ("four", "https://example.test/t", "urn:example:outside#fragment", "External"),
    ))
    graph = build_opc_package_graph(write_package(tmp_path, tuple(package_members)))
    assert [item.id for item in graph.relationships] == ["root", "two", "one", "three", "four"]
    assert all(item.resolved_target is None for item in graph.relationships[1:])


@pytest.mark.parametrize(
    ("package_members", "expected"),
    [
        (members(root_target="missing.xml"), ("missing-internal-target", "_rels/.rels", "Target", "missing.xml")),
        (members(workbook_target="../../escape.xml"), ("invalid-relationship-target", "xl/workbook.xml", "Target", "../../escape.xml")),
        (members() + (("xl/_rels/absent.xml.rels", rels(("x", "https://example.test/t", "x.xml", "Internal"))),), ("invalid-relationship-source", "xl/_rels/absent.xml.rels", "source", "xl/absent.xml")),
        (members() + (("misplaced.rels", rels()),), ("misplaced-relationship-part", "misplaced.rels", "name", "misplaced.rels")),
        (members() + (("xl/%77orkbook.xml", b"<alias/>"),), ("duplicate-normalized-part", "xl/workbook.xml", "name", "xl/%77orkbook.xml")),
        (members() + (("[Content_Types].%78ml", CONTENT_TYPES),), ("duplicate-normalized-part", "[Content_Types].xml", "name", "[Content_Types].%78ml")),
    ],
)
def test_rejects_sources_targets_locations_and_collision_ledger(tmp_path: Path, package_members, expected) -> None:
    assert error(write_package(tmp_path, package_members)) == expected


def test_forbids_canonical_control_and_relationship_targets(tmp_path: Path) -> None:
    assert error(write_package(tmp_path, members(root_target="_rels/.rels")))[0] == "forbidden-internal-target"
    assert error(write_package(tmp_path, members(root_target="%5BContent_Types%5D.%78ml")))[0] == "forbidden-internal-target"


@pytest.mark.parametrize(
    ("package_members", "code"),
    [
        ((("doc.xml", b"<doc/>"),), "missing-content-types"),
        ((("[Content_Types].xml", b"<Types/>"),), "invalid-content-types-root"),
        ((("[Content_Types].xml", b'<?xml version="1.0" encoding="unknown-encoding"?><Types/>'),), "unsupported-xml-encoding"),
        (members() + (("folder/", b""),), "directory-entry"),
    ],
)
def test_validates_content_types_and_members(tmp_path: Path, package_members, code: str) -> None:
    assert error(write_package(tmp_path, package_members))[0] == code


def test_maps_non_zip_corrupt_encrypted_unsupported_relationship_encoding_and_nul_path(tmp_path: Path) -> None:
    non_zip = tmp_path / "not-a-zip.xlsx"; non_zip.write_bytes(b"not zip")
    assert error(non_zip)[0] == "invalid-zip-package"
    corrupt = write_package(tmp_path, (("[Content_Types].xml", CONTENT_TYPES), ("doc.xml", b"payload")), "corrupt.xlsx", ZIP_STORED)
    data = bytearray(corrupt.read_bytes()); data[data.index(b"payload")] ^= 1; corrupt.write_bytes(data)
    assert error(corrupt)[0] == "bad-zip-member"
    encrypted = write_package(tmp_path, (("[Content_Types].xml", CONTENT_TYPES),), "encrypted.xlsx")
    data = bytearray(encrypted.read_bytes())
    for marker, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        data[data.index(marker) + offset] |= 1
    encrypted.write_bytes(data)
    assert error(encrypted)[0] == "encrypted-zip-member"
    bad_rels = list(members()); bad_rels[3] = ("xl/_rels/workbook.xml.rels", b'<?xml version="1.0" encoding="unknown-encoding"?><Relationships/>')
    assert error(write_package(tmp_path, tuple(bad_rels)))[0] == "unsupported-xml-encoding"
    assert error(Path(str(tmp_path / "nul") + "\x00.xlsx"))[0] == "unreadable-package"


def test_replays_corpus_by_expected_mutations_without_fixture_name_branches(tmp_path: Path) -> None:
    for fixture in FIXTURES:
        path = write_fixture(tmp_path / f"{fixture.name}.xlsx", fixture)
        if not fixture.expected_mutations:
            assert build_opc_package_graph(path).parts
        else:
            assert error(path) == fixture.expected_mutations[0]
