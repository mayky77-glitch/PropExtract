"""Implementation-independent direct OPC package corpus for resolver V6.

The corpus deliberately uses only the standard library.  It is a ZIP/XML
oracle, not a wrapper around the product resolver or its lower-level helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "opc-package-v6"

Mutation = tuple[str, str, str, str]


@dataclass(frozen=True)
class PackageFixture:
    name: str
    members: tuple[tuple[str, bytes], ...]
    expected_mutations: tuple[Mutation, ...]


def _relationship_xml(*rows: tuple[str, str, str, str], namespace: str = REL_NS) -> bytes:
    body = "".join(
        '<Relationship Id="%s" Type="%s" Target="%s"%s/>'
        % (identifier, type_uri, target, "" if mode == "Internal" else f' TargetMode="{mode}"')
        for identifier, type_uri, target, mode in rows
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{namespace}">{body}</Relationships>'.encode()


def _content_types_xml() -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="{CONTENT_TYPES_NS}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    ).encode()


def _members(workbook_rels: bytes, *, workbook_name: str = "xl/workbook.xml", rels_name: str = "xl/_rels/workbook.xml.rels") -> tuple[tuple[str, bytes], ...]:
    return (
        ("[Content_Types].xml", _content_types_xml()),
        ("_rels/.rels", _relationship_xml(("rRoot", "http://example.test/officeDocument", workbook_name, "Internal"))),
        (workbook_name, b'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="urn:fixture:spreadsheet"/>'),
        (rels_name, workbook_rels),
        ("xl/worksheets/sheet1.xml", b'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="urn:fixture:spreadsheet"/>'),
    )


_VALID = _relationship_xml(("rSheet", "http://example.test/worksheet", "worksheets/sheet1.xml", "Internal"))

FIXTURES = (
    PackageFixture("valid", _members(_VALID), ()),
    PackageFixture(
        "invalid-part",
        _members(_VALID, workbook_name="xl/../workbook.xml"),
        (("part", "xl/../workbook.xml", "name", "invalid-part-segment"),),
    ),
    PackageFixture(
        "invalid-target",
        _members(_relationship_xml(("rSheet", "http://example.test/worksheet", "../worksheets/sheet1.xml", "Internal"))),
        (("relationship", "xl/workbook.xml", "Target", "../worksheets/sheet1.xml"),),
    ),
    PackageFixture(
        "invalid-type",
        _members(_relationship_xml(("rSheet", "not an absolute URI", "worksheets/sheet1.xml", "Internal"))),
        (("relationship", "xl/workbook.xml", "Type", "not an absolute URI"),),
    ),
    PackageFixture(
        "invalid-id",
        _members(_relationship_xml(("1bad", "http://example.test/worksheet", "worksheets/sheet1.xml", "Internal"))),
        (("relationship", "xl/workbook.xml", "Id", "1bad"),),
    ),
    PackageFixture(
        "invalid-source",
        _members(_VALID, rels_name="xl/_rels/../workbook.xml.rels"),
        (("relationship-part", "xl/_rels/../workbook.xml.rels", "source", "../workbook.xml"),),
    ),
    PackageFixture(
        "invalid-mode",
        _members(_relationship_xml(("rSheet", "http://example.test/worksheet", "worksheets/sheet1.xml", "Remote"))),
        (("relationship", "xl/workbook.xml", "TargetMode", "Remote"),),
    ),
    PackageFixture(
        "invalid-namespace",
        _members(_relationship_xml(("rSheet", "http://example.test/worksheet", "worksheets/sheet1.xml", "Internal"), namespace="urn:wrong-rels")),
        (("relationship-part", "xl/_rels/workbook.xml.rels", "namespace", "urn:wrong-rels"),),
    ),
    PackageFixture(
        "percent-aliases",
        _members(_relationship_xml(("r%53heet", "http://example.test/worksheet", "worksheets/%73heet1.xml", "Internal"))),
        (
            ("relationship", "xl/workbook.xml", "Id", "r%53heet"),
            ("relationship", "xl/workbook.xml", "Target", "worksheets/%73heet1.xml"),
        ),
    ),
    PackageFixture(
        "unicode",
        _members(_relationship_xml(("лист", "http://example.test/worksheet", "worksheets/лист.xml", "Internal"))),
        (
            ("relationship", "xl/workbook.xml", "Id", "лист"),
            ("relationship", "xl/workbook.xml", "Target", "worksheets/лист.xml"),
        ),
    ),
    PackageFixture(
        "controls",
        _members(_relationship_xml(("rSheet", "http://example.test/worksheet", "worksheets/%00sheet1.xml", "Internal"))),
        (("relationship", "xl/workbook.xml", "Target", "worksheets/%00sheet1.xml"),),
    ),
    PackageFixture(
        "encoded-traversal",
        _members(_relationship_xml(("rSheet", "http://example.test/worksheet", "worksheets/%2E%2E/sheet1.xml", "Internal"))),
        (("relationship", "xl/workbook.xml", "Target", "worksheets/%2E%2E/sheet1.xml"),),
    ),
    PackageFixture(
        "ordered-multiple-errors",
        _members(
            _relationship_xml(
                ("1bad", "not an absolute URI", "../worksheets/sheet1.xml", "Internal"),
                ("rSecond", "http://example.test/worksheet", "worksheets/%00sheet1.xml", "Remote"),
            )
        ),
        (
            ("relationship", "xl/workbook.xml", "Id", "1bad"),
            ("relationship", "xl/workbook.xml", "Type", "not an absolute URI"),
            ("relationship", "xl/workbook.xml", "Target", "../worksheets/sheet1.xml"),
            ("relationship", "xl/workbook.xml", "Id", "rSecond"),
            ("relationship", "xl/workbook.xml", "Target", "worksheets/%00sheet1.xml"),
            ("relationship", "xl/workbook.xml", "TargetMode", "Remote"),
        ),
    ),
)


def write_fixture(destination: Path, fixture: PackageFixture) -> Path:
    """Write one deliberately direct, no-production-code OPC ZIP fixture."""
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as package:
        for name, payload in fixture.members:
            package.writestr(name, payload)
    return destination


def package_structure(package_path: Path) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Independently validate ZIP membership and XML root namespaces."""
    with ZipFile(package_path) as package:
        names = tuple(package.namelist())
        roots = tuple((name, ET.fromstring(package.read(name)).tag) for name in names if name.endswith(".xml") or name.endswith(".rels"))
    return names, roots
