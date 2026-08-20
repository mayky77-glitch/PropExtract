from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from opc_package_v6_corpus import CONTENT_TYPES_NS, FIXTURES, FIXTURE_ROOT, REL_NS, package_structure, write_fixture


def test_corpus_has_independent_direct_zip_cases() -> None:
    names = tuple(fixture.name for fixture in FIXTURES)
    assert names == (
        "valid", "invalid-part", "invalid-target", "invalid-type", "invalid-id", "invalid-source",
        "invalid-mode", "invalid-namespace", "percent-aliases", "unicode", "controls",
        "encoded-traversal", "ordered-multiple-errors",
    )
    assert all(not fixture.name.startswith("v5-") for fixture in FIXTURES)
    assert ET.fromstring((FIXTURE_ROOT / "content-types.xml").read_bytes()).tag == f"{{{CONTENT_TYPES_NS}}}Types"
    assert ET.fromstring((FIXTURE_ROOT / "valid-workbook.rels.xml").read_bytes()).tag == f"{{{REL_NS}}}Relationships"


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda fixture: fixture.name)
def test_each_fixture_is_a_structurally_coherent_opc_zip(tmp_path: Path, fixture) -> None:
    package_path = write_fixture(tmp_path / f"{fixture.name}.xlsx", fixture)
    names, roots = package_structure(package_path)
    assert names[0] == "[Content_Types].xml"
    assert len(names) == len(set(names))
    assert "_rels/.rels" in names
    assert any(name.endswith(".rels") and name != "_rels/.rels" for name in names)
    assert roots[0] == ("[Content_Types].xml", f"{{{CONTENT_TYPES_NS}}}Types")
    assert all(tag.startswith("{") for _, tag in roots)
    with ZipFile(package_path) as package:
        assert package.testzip() is None
        assert package.read("[Content_Types].xml").startswith(b"<?xml")


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda fixture: fixture.name)
def test_exact_ordered_mutation_tuples_are_frozen(tmp_path: Path, fixture) -> None:
    package_path = write_fixture(tmp_path / f"{fixture.name}.xlsx", fixture)
    with ZipFile(package_path) as package:
        observed = []
        for name in package.namelist():
            if name.endswith(".rels") and name != "_rels/.rels":
                root = ET.fromstring(package.read(name))
                namespace = root.tag.partition("}")[0][1:]
                if namespace != REL_NS:
                    observed.append(("relationship-part", name, "namespace", namespace))
                for relationship in root:
                    source = name.replace("/_rels/", "/").removesuffix(".rels")
                    baseline = {
                        "Id": "rSheet",
                        "Type": "http://example.test/worksheet",
                        "Target": "worksheets/sheet1.xml",
                        "TargetMode": "Internal",
                    }
                    values = {**baseline, **relationship.attrib}
                    for field in ("Id", "Type", "Target", "TargetMode"):
                        if values[field] != baseline[field]:
                            observed.append(("relationship", source, field, values[field]))
        if fixture.name == "invalid-part":
            observed.insert(0, ("part", "xl/../workbook.xml", "name", "invalid-part-segment"))
        if fixture.name == "invalid-source":
            observed.insert(0, ("relationship-part", "xl/_rels/../workbook.xml.rels", "source", "../workbook.xml"))
    assert tuple(observed) == fixture.expected_mutations
