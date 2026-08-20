from dataclasses import FrozenInstanceError

import pytest

from rns_import_server.opc_workbook_defined_name_reader import (
    OPCWorkbookDefinedNameReaderError,
    read_workbook_defined_name_semantics,
)
from rns_import_server.opc_workbook_topology import OPCWorkbookTopologyError
from tests.opc_workbook_defined_name_fixture_factory import package, workbook


def error(path):
    with pytest.raises((OPCWorkbookDefinedNameReaderError, OPCWorkbookTopologyError)) as caught:
        read_workbook_defined_name_semantics(path)
    return caught.value.as_tuple()


def test_projects_ordered_opaque_names_and_filter_databases(tmp_path):
    names = (
        '<definedNames>'
        '<definedName name="GlobalName">SUM(A1:A2)</definedName>'
        '<definedName name="_xlnm._FilterDatabase" localSheetId=" 0 " hidden="true">Первый!$a$3:$aq$605</definedName>'
        '<definedName name="LocalOpaque" localSheetId="1" hidden="0">formula() + 1</definedName>'
        '<definedName name="_xlnm._FilterDatabase" localSheetId="1" hidden="false">&apos;Лист &apos;&apos;Два&apos;&apos;&apos;!A6:AQ104</definedName>'
        '</definedNames>'
    )
    result = read_workbook_defined_name_semantics(package(tmp_path / "names.xlsx", workbook_xml=workbook(names)))
    assert [(item.name, item.local_sheet_index, item.hidden, item.expression) for item in result.defined_names] == [
        ("GlobalName", None, None, "SUM(A1:A2)"),
        ("_xlnm._FilterDatabase", 0, True, "Первый!$a$3:$aq$605"),
        ("LocalOpaque", 1, False, "formula() + 1"),
        ("_xlnm._FilterDatabase", 1, False, "'Лист ''Два'''!A6:AQ104"),
    ]
    assert [(item.worksheet.name, item.reference.start, item.reference.end, item.reference.min_row, item.reference.max_row) for item in result.filter_databases] == [
        ("Первый", "A3", "AQ605", 3, 605), ("Лист 'Два'", "A6", "AQ104", 6, 104)
    ]
    with pytest.raises(FrozenInstanceError):
        result.filter_databases[0].reference.end = "A606"


@pytest.mark.parametrize(("defined", "expected"), [
    ('<definedNames><definedName name="_xlnm._FilterDatabase">Первый!A3:AQ605</definedName></definedNames>', ("missing-filter-database-scope", "xl/workbook.xml", "localSheetId", "")),
    ('<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">Второй!A3</definedName></definedNames>', ("filter-database-sheet-mismatch", "xl/workbook.xml", "expression", "Второй!A3")),
    ('<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A3,A4</definedName></definedNames>', ("invalid-filter-database-reference", "xl/workbook.xml", "expression", "A3,A4")),
    ('<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!AQ605:A3</definedName></definedNames>', ("invalid-filter-database-reference", "xl/workbook.xml", "expression", "AQ605:A3")),
    ('<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">[Book]Первый!A3</definedName></definedNames>', ("invalid-filter-database-expression", "xl/workbook.xml", "expression", "[Book]Первый!A3")),
])
def test_filter_database_rejects_non_single_sheet_a1(tmp_path, defined, expected):
    assert error(package(tmp_path / "bad-filter.xlsx", workbook_xml=workbook(defined))) == expected


@pytest.mark.parametrize(("defined", "expected"), [
    ('<definedNames><definedName>opaque</definedName></definedNames>', ("missing-defined-name-attribute", "xl/workbook.xml", "attribute", "name")),
    ('<definedNames><definedName name=" ">opaque</definedName></definedNames>', ("blank-defined-name", "xl/workbook.xml", "name", " ")),
    ('<definedNames><definedName name="a" nope="x">opaque</definedName></definedNames>', ("unknown-defined-name-attribute", "xl/workbook.xml", "attribute", "nope")),
    ('<definedNames><definedName name="a">opaque<x/></definedName></definedNames>', ("invalid-defined-name-content", "xl/workbook.xml", "definedName", "nested")),
    ('<definedNames><definedName name="a">opaque</definedName>tail</definedNames>', ("invalid-defined-names-content", "xl/workbook.xml", "definedNames", "tail")),
    ('<definedNames><definedName name="a"/><definedName name="A"/></definedNames>', ("duplicate-defined-name", "xl/workbook.xml", "name", "A")),
    ('<definedNames><definedName name="a" localSheetId="2"/></definedNames>', ("invalid-local-sheet-index", "xl/workbook.xml", "localSheetId", "2")),
    ('<definedNames><definedName name="a" hidden="TRUE"/></definedNames>', ("invalid-defined-name-hidden", "xl/workbook.xml", "hidden", "TRUE")),
])
def test_defined_name_boundary_is_closed(tmp_path, defined, expected):
    assert error(package(tmp_path / "bad-name.xlsx", workbook_xml=workbook(defined))) == expected


def test_namespace_depth_and_container_failures_are_typed(tmp_path):
    collision = b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:x="urn:x"><sheets><sheet name="First" sheetId="1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="one"/></sheets><x:definedNames/></workbook>'
    assert error(package(tmp_path / "collision.xlsx", workbook_xml=collision)) == (
        "owned-defined-name-namespace-collision", "xl/workbook.xml", "tag", "{urn:x}definedNames"
    )
    duplicate = workbook('<definedNames/><definedNames/>')
    assert error(package(tmp_path / "duplicate.xlsx", workbook_xml=duplicate)) == (
        "duplicate-defined-names", "xl/workbook.xml", "definedNames", ""
    )
    illegal = workbook('<definedName name="a"/>')
    assert error(package(tmp_path / "illegal.xlsx", workbook_xml=illegal)) == (
        "invalid-owned-defined-name-parent", "xl/workbook.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}definedName"
    )


def test_filter_scope_and_known_range_owning_builtins_fail_closed(tmp_path):
    duplicate = (
        '<definedNames>'
        '<definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A1</definedName>'
        '<definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A2</definedName>'
        '</definedNames>'
    )
    assert error(package(tmp_path / "duplicate-filter.xlsx", workbook_xml=workbook(duplicate))) == (
        "duplicate-filter-database-scope", "xl/workbook.xml", "localSheetId", "0"
    )
    builtin = '<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">Первый!A1</definedName></definedNames>'
    assert error(package(tmp_path / "builtin.xlsx", workbook_xml=workbook(builtin))) == (
        "unsupported-range-owning-built-in", "xl/workbook.xml", "name", "_xlnm.Print_Area"
    )


class _Once:
    def __init__(self, value): self.value = value; self.calls = 0
    def __fspath__(self):
        self.calls += 1
        if self.calls == 1: return self.value
        raise TypeError("called twice")


class _PathFailure:
    def __fspath__(self):
        raise RuntimeError("broken")


@pytest.mark.parametrize(("value", "expected"), [
    (b"book.xlsx", ("invalid-package-path", "builtins.bytes", "path", "bytes")),
    ("bad\x00.xlsx", ("unreadable-package", "bad\x00.xlsx", "path", "embedded-nul")),
    (_PathFailure(), ("unreadable-package", f"{__name__}._PathFailure", "path", "RuntimeError")),
])
def test_path_boundary_is_typed(value, expected):
    assert error(value) == expected


def test_coerces_once_and_forwards_topology_errors(tmp_path):
    value = _Once(str(package(tmp_path / "once.xlsx")))
    assert read_workbook_defined_name_semantics(value).defined_names == ()
    assert value.calls == 1
    assert error(package(tmp_path / "broken.xlsx", workbook_xml=b"<workbook")) == (
        "malformed-workbook-xml", "xl/workbook.xml", "xml", "xml"
    )


def test_requires_raw_canonical_workbook_member(tmp_path):
    assert error(package(tmp_path / "alias.xlsx", workbook_member="xl/work%62ook.xml")) == (
        "noncanonical-workbook-member", "xl/workbook.xml", "member", "xl/work%62ook.xml"
    )
