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


@pytest.mark.parametrize("attribute", ["hidden", "function", "vbProcedure", "xlm", "publishToServer", "workbookParameter"])
@pytest.mark.parametrize("lexical", ["0", "1", "false", "true"])
def test_all_allowlisted_native_boolean_attributes_accept_exact_xml_lexicals(tmp_path, attribute, lexical):
    defined = f'<definedNames><definedName name="opaque" {attribute}="{lexical}">anything</definedName></definedNames>'
    result = read_workbook_defined_name_semantics(package(tmp_path / f"{attribute}-{lexical}.xlsx", workbook_xml=workbook(defined)))
    assert [(item.name, item.expression) for item in result.defined_names] == [("opaque", "anything")]


@pytest.mark.parametrize("attribute", ["hidden", "function", "vbProcedure", "xlm", "publishToServer", "workbookParameter"])
def test_filter_databases_accept_all_allowlisted_native_boolean_attributes(tmp_path, attribute):
    defined = (
        f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" {attribute}="true">'
        'Первый!A1:A2</definedName></definedNames>'
    )
    result = read_workbook_defined_name_semantics(package(tmp_path / f"filter-{attribute}.xlsx", workbook_xml=workbook(defined)))
    assert (result.filter_databases[0].reference.start, result.filter_databases[0].reference.end) == ("A1", "A2")


@pytest.mark.parametrize("attribute", ["hidden", "function", "vbProcedure", "xlm", "publishToServer", "workbookParameter"])
@pytest.mark.parametrize("lexical", ["", "TRUE", "False", "maybe", " 1", "1 "])
def test_all_allowlisted_native_boolean_attributes_fail_with_exact_tuple(tmp_path, attribute, lexical):
    defined = f'<definedNames><definedName name="opaque" {attribute}="{lexical}">anything</definedName></definedNames>'
    expected_code = "invalid-defined-name-hidden" if attribute == "hidden" else "invalid-defined-name-boolean"
    assert error(package(tmp_path / f"bad-{attribute}.xlsx", workbook_xml=workbook(defined))) == (
        expected_code, "xl/workbook.xml", attribute, lexical
    )


def test_invalid_native_boolean_precedes_filter_mapping(tmp_path):
    defined = (
        '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" function="maybe">'
        'Первый!A1</definedName></definedNames>'
    )
    assert error(package(tmp_path / "filter-boolean.xlsx", workbook_xml=workbook(defined))) == (
        "invalid-defined-name-boolean", "xl/workbook.xml", "function", "maybe"
    )


@pytest.mark.parametrize("attribute", ["hidden", "function", "vbProcedure", "xlm", "publishToServer", "workbookParameter"])
def test_invalid_filter_native_boolean_is_typed_before_filter_success(tmp_path, attribute):
    defined = (
        f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" {attribute}="maybe">'
        'Первый!A1</definedName></definedNames>'
    )
    expected_code = "invalid-defined-name-hidden" if attribute == "hidden" else "invalid-defined-name-boolean"
    assert error(package(tmp_path / f"filter-bad-{attribute}.xlsx", workbook_xml=workbook(defined))) == (
        expected_code, "xl/workbook.xml", attribute, "maybe"
    )


@pytest.mark.parametrize("lexical", ["0", "+4294967295", " \t1\n"])
def test_function_group_id_accepts_bounded_xml_whitespace_unsigned_integer(tmp_path, lexical):
    defined = f'<definedNames><definedName name="opaque" functionGroupId="{lexical}">x</definedName></definedNames>'
    assert read_workbook_defined_name_semantics(package(tmp_path / "group-ok.xlsx", workbook_xml=workbook(defined))).defined_names[0].name == "opaque"


@pytest.mark.parametrize("lexical", ["", "-0", "4294967296", "+4294967296", "1.0", "1 2"])
def test_function_group_id_rejects_non_unsigned_or_out_of_bounds_lexicals(tmp_path, lexical):
    defined = f'<definedNames><definedName name="opaque" functionGroupId="{lexical}">x</definedName></definedNames>'
    assert error(package(tmp_path / "group-bad.xlsx", workbook_xml=workbook(defined))) == (
        "invalid-defined-name-function-group-id", "xl/workbook.xml", "functionGroupId", lexical
    )


def test_quote_aware_filter_delimiter_accepts_bang_in_quoted_topology_sheet_name(tmp_path):
    sheets = (
        '<sheet name="Bang!Sheet" sheetId="1" r:id="one"/>'
        '<sheet name="Other" sheetId="2" r:id="two"/>'
    )
    defined = '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">&apos;Bang!Sheet&apos;!A1:A2</definedName></definedNames>'
    result = read_workbook_defined_name_semantics(package(tmp_path / "bang.xlsx", workbook_xml=workbook(defined, sheets)))
    item = result.filter_databases[0]
    assert (item.worksheet.name, item.reference.start, item.reference.end) == ("Bang!Sheet", "A1", "A2")


@pytest.mark.parametrize("expression", [
    "'Bang!Sheet!A1", "'Bang!Sheet'!A1!A2", "Bang!!Sheet!A1", "'Bang'Sheet'!A1", "Bang!Sheet!A1",
])
def test_quote_aware_filter_delimiter_rejects_ambiguous_or_multiple_delimiters(tmp_path, expression):
    sheets = (
        '<sheet name="Bang!Sheet" sheetId="1" r:id="one"/>'
        '<sheet name="Other" sheetId="2" r:id="two"/>'
    )
    defined = f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">{expression}</definedName></definedNames>'
    assert error(package(tmp_path / "bad-bang.xlsx", workbook_xml=workbook(defined, sheets))) == (
        "invalid-filter-database-expression", "xl/workbook.xml", "expression", expression
    )


@pytest.mark.parametrize("expression", [
    "Первый!A1,A2", "Первый:Второй!A1", "[Book]Первый!A1", "Первый!SUM(A1)",
    "Первый!#REF!", "Первый!A:A", "Первый!1:1", "Первый!XFE1", "Первый!A1048577",
    "'Первый!A1", "'Первый'x'!A1", "=Первый!A1",
])
def test_filter_database_full_rejection_matrix(tmp_path, expression):
    defined = f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">{expression}</definedName></definedNames>'
    captured = error(package(tmp_path / "matrix.xlsx", workbook_xml=workbook(defined)))
    assert captured[:3] in {
        ("invalid-filter-database-expression", "xl/workbook.xml", "expression"),
        ("invalid-filter-database-reference", "xl/workbook.xml", "expression"),
    }


@pytest.mark.parametrize(("payload", "expected"), [
    (b"<workbook", ("malformed-workbook-xml", "xl/workbook.xml", "xml", "xml")),
    (b'<?xml version="1.0" encoding="UTF-7"?><workbook/>', ("unsupported-xml-encoding", "xl/workbook.xml", "xml", "encoding")),
    (b"<workbook/>", ("invalid-workbook-root", "xl/workbook.xml", "root", "workbook")),
    (b'<workbook xmlns="urn:foreign"/>', ("invalid-workbook-root", "xl/workbook.xml", "root", "{urn:foreign}workbook")),
])
def test_dependency_xml_failures_forward_the_original_typed_tuple(tmp_path, payload, expected):
    with pytest.raises(OPCWorkbookTopologyError) as caught:
        read_workbook_defined_name_semantics(package(tmp_path / "dependency-xml.xlsx", workbook_xml=payload))
    assert caught.value.as_tuple() == expected


def test_utf8_declaration_and_bom_are_accepted_without_changing_projection(tmp_path):
    source = workbook('<definedNames><definedName name="opaque">x</definedName></definedNames>')
    declaration = b'<?xml version="1.0" encoding="UTF-8"?>' + source
    bom = b"\xef\xbb\xbf" + declaration
    for label, payload in (("declaration", declaration), ("bom", bom)):
        result = read_workbook_defined_name_semantics(package(tmp_path / f"{label}.xlsx", workbook_xml=payload))
        assert [(item.name, item.expression) for item in result.defined_names] == [("opaque", "x")]


def test_member_collision_and_missing_member_fail_at_accepted_topology_boundary(tmp_path):
    collision = package(
        tmp_path / "collision.xlsx", extra_members=(("xl/work%62ook.xml", workbook()),),
    )
    with pytest.raises(OPCWorkbookTopologyError) as caught:
        read_workbook_defined_name_semantics(collision)
    assert caught.value.as_tuple() == ("duplicate-normalized-part", "xl/workbook.xml", "name", "xl/work%62ook.xml")
    missing = package(tmp_path / "missing.xlsx", workbook_member="xl/missing.xml")
    with pytest.raises(OPCWorkbookTopologyError) as caught:
        read_workbook_defined_name_semantics(missing)
    assert caught.value.as_tuple() == ("missing-internal-target", "_rels/.rels", "Target", "xl/workbook.xml")


def test_unsafe_member_name_fails_at_the_accepted_topology_boundary(tmp_path):
    unsafe = package(tmp_path / "unsafe.xlsx", extra_members=(("xl\\unsafe.xml", b"x"),))
    with pytest.raises(OPCWorkbookTopologyError) as caught:
        read_workbook_defined_name_semantics(unsafe)
    assert caught.value.as_tuple() == ("invalid-part-uri", "xl\\unsafe.xml", "name", "invalid-backslash")


@pytest.mark.parametrize(("defined", "expected"), [
    ('<definedNames nope="x"/>', ("unknown-defined-names-attribute", "xl/workbook.xml", "attribute", "nope")),
    ('<definedNames>text</definedNames>', ("invalid-defined-names-content", "xl/workbook.xml", "definedNames", "text")),
    ('<definedNames><other/></definedNames>', ("invalid-defined-names-child", "xl/workbook.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}other")),
    ('<ext><definedNames/></ext>', ("invalid-owned-defined-name-parent", "xl/workbook.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}definedNames")),
    ('<definedNames><definedName name="a"><definedName name="b"/></definedName></definedNames>', ("invalid-owned-defined-name-parent", "xl/workbook.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}definedName")),
    ('<definedNames/>tail', ("invalid-defined-names-content", "xl/workbook.xml", "definedNames", "tail")),
])
def test_every_owned_container_parent_child_text_and_tail_boundary_is_typed(tmp_path, defined, expected):
    assert error(package(tmp_path / "owned-boundary.xlsx", workbook_xml=workbook(defined))) == expected


@pytest.mark.parametrize(("fragment", "tag"), [
    ('<x:definedNames/>', "{urn:foreign}definedNames"),
    ('<definedNames><x:definedName name="a"/></definedNames>', "{urn:foreign}definedName"),
    ('<definedNames xmlns=""><definedName name="a"/></definedNames>', "definedNames"),
])
def test_every_owned_namespace_collision_is_typed(tmp_path, fragment, tag):
    payload = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:x="urn:foreign">'
        '<sheets><sheet name="Первый" sheetId="1" r:id="one"/><sheet name="Лист &apos;Два&apos;" sheetId="2" r:id="two"/></sheets>'
        + fragment + '</workbook>'
    ).encode()
    assert error(package(tmp_path / "namespace.xlsx", workbook_xml=payload)) == (
        "owned-defined-name-namespace-collision", "xl/workbook.xml", "tag", tag
    )


@pytest.mark.parametrize("lexical", ["", "-0", "2", "4294967296", "1.0", "1 0"])
def test_local_sheet_id_invalid_lexicals_and_bounds_are_closed(tmp_path, lexical):
    defined = f'<definedNames><definedName name="opaque" localSheetId="{lexical}">x</definedName></definedNames>'
    assert error(package(tmp_path / "local-bad.xlsx", workbook_xml=workbook(defined))) == (
        "invalid-local-sheet-index", "xl/workbook.xml", "localSheetId", lexical
    )


def test_local_sheet_id_xml_whitespace_and_opaque_local_scopes_are_preserved(tmp_path):
    defined = (
        '<definedNames><definedName name="same" localSheetId=" +0 ">one</definedName>'
        '<definedName name="same" localSheetId="1">two</definedName></definedNames>'
    )
    result = read_workbook_defined_name_semantics(package(tmp_path / "local-ok.xlsx", workbook_xml=workbook(defined)))
    assert [(item.name, item.local_sheet_index, item.expression) for item in result.defined_names] == [
        ("same", 0, "one"), ("same", 1, "two")
    ]


def test_filter_database_insertion_evidence_does_not_mutate_the_source_range(tmp_path):
    defined = '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0">Первый!A3:AQ605</definedName></definedNames>'
    result = read_workbook_defined_name_semantics(package(tmp_path / "insertion-evidence.xlsx", workbook_xml=workbook(defined)))
    source = result.filter_databases[0].reference
    candidates = []
    for insertion_row in (6, 10, 104):
        candidates.append((source.start, f"AQ{source.max_row + (1 if source.max_row >= insertion_row else 0)}"))
    assert (source.start, source.end, source.min_row, source.max_row) == ("A3", "AQ605", 3, 605)
    assert candidates == [("A3", "AQ606"), ("A3", "AQ606"), ("A3", "AQ606")]
