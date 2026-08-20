from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from opc_package_v6_corpus import FIXTURES, write_fixture
from rns_import_server.opc_package_graph import (
    CONTENT_TYPES_NAMESPACE,
    OPCPackageGraphError,
    build_opc_package_graph,
)
from rns_import_server.opc_part_uri import CanonicalPartURI


CONTENT_TYPES = (
    f'<Types xmlns="{CONTENT_TYPES_NAMESPACE}"><Default Extension="xml" '
    'ContentType="application/xml"/></Types>'
).encode()
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def rels(*rows: tuple[str, str, str, str]) -> bytes:
    body = "".join(
        '<Relationship Id="%s" Type="%s" Target="%s"%s/>'
        % (identifier, type_uri, target, "" if mode == "Internal" else f' TargetMode="{mode}"')
        for identifier, type_uri, target, mode in rows
    )
    return f'<Relationships xmlns="{REL_NS}">{body}</Relationships>'.encode()


def package(
    tmp_path: Path,
    members: tuple[tuple[str, bytes], ...],
    name: str = "package.xlsx",
    compression: int = ZIP_DEFLATED,
) -> Path:
    destination = tmp_path / name
    with ZipFile(destination, "w", compression=compression) as archive:
        for member, payload in members:
            archive.writestr(member, payload)
    return destination


def valid_members(*, root_target: str = "xl/workbook.xml", workbook_target: str = "worksheets/sheet1.xml") -> tuple[tuple[str, bytes], ...]:
    return (
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", rels(("rRoot", "https://example.test/root", root_target, "Internal"))),
        ("xl/workbook.xml", b"<workbook/>"),
        ("xl/_rels/workbook.xml.rels", rels(("rSheet", "https://example.test/sheet", workbook_target, "Internal"))),
        ("xl/worksheets/sheet1.xml", b"<worksheet/>"),
    )


def error_tuple(path: Path) -> tuple[str, str, str, str]:
    with pytest.raises(OPCPackageGraphError) as caught:
        build_opc_package_graph(path)
    return caught.value.as_tuple()


def test_builds_ordered_immutable_graph_with_root_and_nested_relationships(tmp_path: Path) -> None:
    path = package(tmp_path, valid_members())
    graph = build_opc_package_graph(path)
    assert [part.name for part in graph.parts] == [
        CanonicalPartURI("xl/workbook.xml"),
        CanonicalPartURI("xl/worksheets/sheet1.xml"),
    ]
    assert [
        (item.relationship_part.value, item.source.value if item.source else None, item.id, item.target, item.resolved_target.value if item.resolved_target else None)
        for item in graph.relationships
    ] == [
        ("_rels/.rels", None, "rRoot", "xl/workbook.xml", "xl/workbook.xml"),
        ("xl/_rels/workbook.xml.rels", "xl/workbook.xml", "rSheet", "worksheets/sheet1.xml", "xl/worksheets/sheet1.xml"),
    ]
    assert graph.relationships[1].source_part == CanonicalPartURI("xl/workbook.xml")
    with pytest.raises(FrozenInstanceError):
        graph.parts[0].name = CanonicalPartURI("other.xml")  # type: ignore[misc]


def test_preserves_zip_member_and_relationship_xml_order(tmp_path: Path) -> None:
    members = valid_members()
    altered = (
        members[0], members[1], members[2],
        ("xl/_rels/workbook.xml.rels", rels(("rSecond", "https://example.test/t", "worksheets/sheet1.xml", "Internal"), ("rFirst", "https://example.test/t", "worksheets/sheet1.xml", "Internal"))),
        members[4], ("doc.xml", b"<doc/>"),
    )
    graph = build_opc_package_graph(package(tmp_path, altered))
    assert [part.name.value for part in graph.parts] == ["xl/workbook.xml", "xl/worksheets/sheet1.xml", "doc.xml"]
    assert [item.id for item in graph.relationships] == ["rRoot", "rSecond", "rFirst"]


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        (valid_members(root_target="missing.xml"), ("missing-internal-target", "_rels/.rels", "Target", "missing.xml")),
        (valid_members(workbook_target="../../escape.xml"), ("invalid-relationship-target", "xl/workbook.xml", "Target", "../../escape.xml")),
        (valid_members() + (("xl/_rels/absent.xml.rels", rels(("r", "https://example.test/t", "x.xml", "Internal"))),), ("invalid-relationship-source", "xl/_rels/absent.xml.rels", "source", "xl/absent.xml")),
        (valid_members() + (("misplaced.rels", rels()),), ("misplaced-relationship-part", "misplaced.rels", "name", "misplaced.rels")),
        (valid_members() + (("xl/%77orkbook.xml", b"<alias/>"),), ("duplicate-normalized-part", "xl/workbook.xml", "name", "xl/%77orkbook.xml")),
        (valid_members() + (("xl/../bad.xml", b"<bad/>"),), ("invalid-part-uri", "xl/../bad.xml", "name", "invalid-part-segment")),
    ],
)
def test_rejects_invalid_members_sources_targets_and_relationship_locations(tmp_path: Path, members, expected) -> None:
    assert error_tuple(package(tmp_path, members)) == expected


def test_external_uri_references_stay_external_and_are_not_resolved(tmp_path: Path) -> None:
    members = list(valid_members())
    members[3] = (
        "xl/_rels/workbook.xml.rels",
        rels(
            ("relative", "https://example.test/t", "../outside.xml", "External"),
            ("rooted", "https://example.test/t", "/outside.xml", "External"),
            ("network", "https://example.test/t", "//host/outside.xml", "External"),
            ("absolute", "https://example.test/t", "urn:example:outside#fragment", "External"),
        ),
    )
    graph = build_opc_package_graph(package(tmp_path, tuple(members)))
    assert [item.resolved_target for item in graph.relationships[1:]] == [None, None, None, None]
    assert [item.target for item in graph.relationships[1:]] == ["../outside.xml", "/outside.xml", "//host/outside.xml", "urn:example:outside#fragment"]


@pytest.mark.parametrize(
    ("members", "expected_code"),
    [
        ((("doc.xml", b"<doc/>"),), "missing-content-types"),
        ((("[Content_Types].xml", b"<Types/>"),), "invalid-content-types-root"),
        ((("[Content_Types].xml", b"<Types"),), "malformed-content-types"),
        (valid_members() + (("folder/", b""),), "directory-entry"),
    ],
)
def test_validates_content_types_and_directory_entries(tmp_path: Path, members, expected_code: str) -> None:
    assert error_tuple(package(tmp_path, members))[0] == expected_code


def test_rejects_corrupt_non_zip_and_encrypted_input(tmp_path: Path) -> None:
    non_zip = tmp_path / "not-a-zip.xlsx"
    non_zip.write_bytes(b"not a zip")
    assert error_tuple(non_zip)[0] == "invalid-zip-package"

    corrupt = package(
        tmp_path,
        (("[Content_Types].xml", CONTENT_TYPES), ("doc.xml", b"payload")),
        "corrupt.xlsx",
        ZIP_STORED,
    )
    payload = bytearray(corrupt.read_bytes())
    payload[payload.index(b"payload")] ^= 1
    corrupt.write_bytes(payload)
    assert error_tuple(corrupt)[0] == "bad-zip-member"

    encrypted = package(tmp_path, (("[Content_Types].xml", CONTENT_TYPES),), "encrypted.xlsx")
    data = bytearray(encrypted.read_bytes())
    for marker, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = data.index(marker)
        data[start + offset] |= 1
    encrypted.write_bytes(data)
    assert error_tuple(encrypted)[0] == "encrypted-zip-member"


def test_forbids_internal_targets_to_control_parts(tmp_path: Path) -> None:
    assert error_tuple(package(tmp_path, valid_members(root_target="_rels/.rels")))[0] == "forbidden-internal-target"
    assert error_tuple(package(tmp_path, valid_members(root_target="[Content_Types].xml")))[0] == "invalid-relationship-target"


def test_corpus_packages_have_a_stable_first_success_or_failure_category(tmp_path: Path) -> None:
    expected = {
        "invalid-part": "invalid-part-uri",
        "invalid-target": "invalid-relationship-target",
        "invalid-type": "invalid-relationship-type",
        "invalid-id": "invalid-relationship-id",
        "invalid-source": "invalid-part-uri",
        "invalid-mode": "invalid-target-mode",
        "invalid-namespace": "invalid-relationships-root",
        "controls": "invalid-relationship-target",
        "encoded-traversal": "invalid-relationship-target",
        "ordered-multiple-errors": "invalid-relationship-id",
    }
    for fixture in FIXTURES:
        path = write_fixture(tmp_path / f"{fixture.name}.xlsx", fixture)
        if fixture.name in {"valid", "percent-alias"}:
            assert build_opc_package_graph(path).parts
        elif fixture.name == "unicode":
            # The accepted relationship XML primitive is intentionally ASCII
            # URI-reference strict, so it is the responsible boundary here.
            assert error_tuple(path)[0] == "invalid-relationship-target"
        else:
            assert error_tuple(path)[0] == expected[fixture.name]
