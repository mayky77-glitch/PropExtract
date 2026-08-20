from __future__ import annotations

import pytest

from rns_import_server.opc_workbook_topology import OPCWorkbookTopologyError, read_workbook_topology
from tests.opc_workbook_fixture_factory import OFFICE_REL_NS, SHEET_NS, package, relationship


def error_tuple(path):
    with pytest.raises(OPCWorkbookTopologyError) as captured:
        read_workbook_topology(path)
    return captured.value.as_tuple()


def workbook(sheets: str) -> bytes:
    return f'<workbook xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets>{sheets}</sheets></workbook>'.encode()


def test_reads_ordered_immutable_unicode_topology(tmp_path):
    xml = workbook('<sheet name="Главный" sheetId="6" r:id="first" state="hidden"/>'
                   '<sheet name="Граница" sheetId="10" r:id="second" state="veryHidden"/>'
                   '<sheet name="Данные" sheetId="104" r:id="third"/>')
    rels = relationship("first", f"{OFFICE_REL_NS}/worksheet", "worksheets/главный.xml") + relationship("second", f"{OFFICE_REL_NS}/worksheet", "worksheets/boundary.xml") + relationship("third", f"{OFFICE_REL_NS}/worksheet", "worksheets/data.xml")
    result = read_workbook_topology(package(tmp_path / "book.xlsx", workbook_xml=xml, workbook_relationships=rels, worksheet_parts=("xl/worksheets/главный.xml", "xl/worksheets/boundary.xml", "xl/worksheets/data.xml")))
    assert [(item.name, item.sheet_id, item.state, item.relationship_id, item.worksheet_part.value) for item in result.worksheets] == [("Главный", 6, "hidden", "first", "xl/worksheets/главный.xml"), ("Граница", 10, "veryHidden", "second", "xl/worksheets/boundary.xml"), ("Данные", 104, "visible", "third", "xl/worksheets/data.xml")]
    with pytest.raises(AttributeError): result.worksheets[0].name = "other"


@pytest.mark.parametrize(("sheets", "expected"), [
    ('<sheet name="A" sheetId="0" r:id="one"/>', ("invalid-sheet-id", "xl/workbook.xml", "sheetId", "0")),
    ('<sheet name="A" sheetId="1" r:id="one"/><sheet name="A" sheetId="2" r:id="two"/>', ("duplicate-sheet-name", "xl/workbook.xml", "name", "A")),
    ('<sheet name="A" sheetId="1" r:id="one"/><sheet name="B" sheetId="1" r:id="two"/>', ("duplicate-sheet-id", "xl/workbook.xml", "sheetId", "1")),
    ('<sheet name="A" sheetId="1" r:id="one"/><sheet name="B" sheetId="2" r:id="one"/>', ("duplicate-sheet-relationship-id", "xl/workbook.xml", "r:id", "one")),
])
def test_rejects_duplicate_or_invalid_sheet_identity(tmp_path, sheets, expected):
    rels = relationship("one", f"{OFFICE_REL_NS}/worksheet", "worksheets/sheet1.xml") + relationship("two", f"{OFFICE_REL_NS}/worksheet", "worksheets/sheet2.xml")
    assert error_tuple(package(tmp_path / "book.xlsx", workbook_xml=workbook(sheets), workbook_relationships=rels, worksheet_parts=("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"))) == expected


def test_rejects_missing_or_external_sheet_relationship(tmp_path):
    xml = workbook('<sheet name="A" sheetId="1" r:id="missing"/>')
    assert error_tuple(package(tmp_path / "missing.xlsx", workbook_xml=xml)) == ("missing-sheet-relationship", "xl/workbook.xml", "r:id", "missing")
    rels = relationship("missing", f"{OFFICE_REL_NS}/worksheet", "https://example.test/sheet", "External")
    assert error_tuple(package(tmp_path / "external.xlsx", workbook_xml=xml, workbook_relationships=rels)) == ("external-sheet-relationship", "xl/workbook.xml", "r:id", "missing")


def test_rejects_invalid_root_and_unsupported_encoding(tmp_path):
    assert error_tuple(package(tmp_path / "root.xlsx", workbook_xml=b"<bad/>")) == ("invalid-workbook-root", "xl/workbook.xml", "root", "bad")
    encoded = b'<?xml version="1.0" encoding="utf-7"?><workbook xmlns="' + SHEET_NS.encode() + b'"/>'
    assert error_tuple(package(tmp_path / "encoding.xlsx", workbook_xml=encoded)) == ("unsupported-xml-encoding", "xl/workbook.xml", "xml", "encoding")


@pytest.mark.parametrize(("xml", "expected"), [
    (f'<workbook xmlns="{SHEET_NS}"/>'.encode(), ("missing-sheets", "xl/workbook.xml", "sheets", "")),
    (f'<workbook xmlns="{SHEET_NS}"><sheets/><sheets/></workbook>'.encode(), ("duplicate-sheets", "xl/workbook.xml", "sheets", "")),
    (workbook('<sheet name="A" sheetId="1" r:id="rSheet1" extra="x"/>'), ("unknown-sheet-attribute", "xl/workbook.xml", "attribute", "extra")),
])
def test_rejects_invalid_sheets_structure(tmp_path, xml, expected):
    assert error_tuple(package(tmp_path / "structure.xlsx", workbook_xml=xml)) == expected


def test_requires_supported_main_workbook_content_type(tmp_path):
    assert error_tuple(package(tmp_path / "missing.xlsx", workbook_content_type=None)) == ("missing-workbook-content-type", "xl/workbook.xml", "PartName", "/xl/workbook.xml")
    assert error_tuple(package(tmp_path / "wrong.xlsx", workbook_content_type="application/xml")) == ("unsupported-workbook-content-type", "xl/workbook.xml", "ContentType", "application/xml")


def test_rejects_non_worksheet_and_ambiguous_mapping(tmp_path):
    xml = workbook('<sheet name="A" sheetId="1" r:id="rSheet1"/>')
    wrong = relationship("rSheet1", "https://example.test/not-sheet", "worksheets/sheet1.xml")
    assert error_tuple(package(tmp_path / "wrong.xlsx", workbook_xml=xml, workbook_relationships=wrong)) == ("non-worksheet-relationship", "xl/workbook.xml", "r:id", "rSheet1")
    duplicate = relationship("rSheet1", f"{OFFICE_REL_NS}/worksheet", "worksheets/sheet1.xml") + relationship("rSheet1", f"{OFFICE_REL_NS}/worksheet", "worksheets/sheet1.xml")
    assert error_tuple(package(tmp_path / "duplicate.xlsx", workbook_xml=xml, workbook_relationships=duplicate)) == ("duplicate-relationship-id", "xl/workbook.xml", "xml", "rSheet1")
