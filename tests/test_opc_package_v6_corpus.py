from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import pytest
from opc_package_v6_corpus import CONTENT_TYPES_INPUT, CONTENT_TYPES_NS, FIXTURES, REL_NS, VALID_WORKBOOK_RELS_INPUT, fixture_hash, mutation_tuples, package_structure, write_fixture

def test_committed_xml_is_actual_input() -> None:
    valid = FIXTURES[0]
    assert valid.members[0] == ("[Content_Types].xml", CONTENT_TYPES_INPUT.read_bytes())
    assert valid.members[3] == ("xl/_rels/workbook.xml.rels", VALID_WORKBOOK_RELS_INPUT.read_bytes())
    assert ET.fromstring(CONTENT_TYPES_INPUT.read_bytes()).tag == f"{{{CONTENT_TYPES_NS}}}Types"
    assert ET.fromstring(VALID_WORKBOOK_RELS_INPUT.read_bytes()).tag == f"{{{REL_NS}}}Relationships"

@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_exact_manifest_content_types_and_structure(tmp_path: Path, fixture) -> None:
    path = write_fixture(tmp_path / f"{fixture.name}.xlsx", fixture); names, roots = package_structure(path)
    assert names == fixture.manifest and len(names) == len(set(names)) and all(tag.startswith("{") for _, tag in roots)
    with ZipFile(path) as z:
        assert z.testzip() is None
        root = ET.fromstring(z.read("[Content_Types].xml"))
        assert tuple((n.tag, tuple(sorted(n.attrib.items()))) for n in root) == (
            (f"{{{CONTENT_TYPES_NS}}}Default", (("ContentType", "application/vnd.openxmlformats-package.relationships+xml"), ("Extension", "rels"))),
            (f"{{{CONTENT_TYPES_NS}}}Default", (("ContentType", "application/xml"), ("Extension", "xml"))),
            (f"{{{CONTENT_TYPES_NS}}}Override", (("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"), ("PartName", "/xl/workbook.xml"))),
            (f"{{{CONTENT_TYPES_NS}}}Override", (("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"), ("PartName", "/xl/worksheets/sheet1.xml"))),
        )

@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_complete_ordered_byte_derived_tuples(tmp_path: Path, fixture) -> None:
    assert mutation_tuples(write_fixture(tmp_path / "case.xlsx", fixture)) == fixture.expected_mutations

def test_zip_metadata_and_bytes_are_reproducible(tmp_path: Path) -> None:
    a = write_fixture(tmp_path / "a.xlsx", FIXTURES[0]); b = write_fixture(tmp_path / "b.xlsx", FIXTURES[0])
    assert fixture_hash(a) == fixture_hash(b)
    with ZipFile(a) as z: assert all(i.date_time == (1980, 1, 1, 0, 0, 0) and i.create_system == 3 and i.external_attr == 0o100644 << 16 for i in z.infolist())

def test_meta_omitted_target_missing_attribute_and_source_fail(tmp_path: Path) -> None:
    valid = FIXTURES[0]; cls = valid.__class__
    no_target = cls("meta", tuple(x for x in valid.members if x[0] != "xl/worksheets/sheet1.xml"), ())
    assert mutation_tuples(write_fixture(tmp_path / "no-target.xlsx", no_target)) == (("missing-internal-target", "xl/workbook.xml", "Target", "worksheets/sheet1.xml"),)
    rels = b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rSheet" Type="http://example.test/worksheet"/></Relationships>'
    no_attr = cls("meta", tuple((n, rels if n.endswith("workbook.xml.rels") else p) for n, p in valid.members), ())
    assert mutation_tuples(write_fixture(tmp_path / "no-attr.xlsx", no_attr)) == (("missing-relationship-attribute", "xl/_rels/workbook.xml.rels", "Target", ""),)
    no_source = cls("meta", tuple(("xl/_rels/absent.xml.rels", p) if n.endswith("workbook.xml.rels") else (n, p) for n, p in valid.members), ())
    assert mutation_tuples(write_fixture(tmp_path / "no-source.xlsx", no_source)) == (("invalid-relationship-source", "xl/_rels/absent.xml.rels", "source", "xl/absent.xml"),)
