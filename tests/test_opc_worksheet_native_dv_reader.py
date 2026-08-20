from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import rns_import_server.opc_worksheet_native_dv_reader as reader
from rns_import_server.opc_worksheet_native_dv_reader import (
    OPCWorksheetNativeDvReaderError,
    read_worksheet_native_data_validation_semantics,
)
from rns_import_server.opc_workbook_topology import OPCWorkbookTopologyError
from rns_import_server.opc_workbook_topology import WorkbookTopology, WorksheetDescriptor
from rns_import_server.opc_part_uri import CanonicalPartURI
from tests.opc_worksheet_native_dv_fixture_factory import package, worksheet


def error(path):
    with pytest.raises((OPCWorksheetNativeDvReaderError, OPCWorkbookTopologyError)) as captured:
        read_worksheet_native_data_validation_semantics(path)
    return captured.value.as_tuple()


PART = CanonicalPartURI("xl/worksheets/first.xml")


def isolated_topology(monkeypatch, part=PART):
    topology = WorkbookTopology(
        CanonicalPartURI("xl/workbook.xml"),
        (WorksheetDescriptor("First", 1, "visible", "one", part),),
    )
    monkeypatch.setattr(reader, "read_workbook_topology", lambda path: topology)


def test_reads_all_native_fields_in_topology_order_and_is_immutable(tmp_path):
    first = worksheet(
        '<dataValidations count="2" disablePrompts="false" xWindow=" +42 " yWindow="-0">'
        '<dataValidation sqref="A6 B10:C10" type="whole" operator="between" allowBlank="0" showDropDown="true" showInputMessage="false" showErrorMessage="1" errorStyle="warning" imeMode="hiragana" errorTitle="Bad" error="No" promptTitle="Hint" prompt="Enter" xr:uid="{01234567-89ab-cdef-0123-456789abcdef}"><formula1>1</formula1><formula2>9</formula2></dataValidation>'
        '<dataValidation sqref="R104:R154 S104:S159 XFD104" type="list"><formula1>"A,B"</formula1></dataValidation>'
        '</dataValidations>'
    )
    result = read_worksheet_native_data_validation_semantics(package(tmp_path / "ok.xlsx", sheet_one=first))
    assert [item.worksheet.name for item in result.worksheets] == ["Первый", "Второй"]
    container = result.worksheets[0].container
    assert container is not None
    assert (container.owner_path, container.count, container.disable_prompts, container.x_window, container.y_window) == (
        "xl/worksheets/first.xml/worksheet/dataValidations", 2, False, 42, 0,
    )
    rule = container.rules[0]
    assert (rule.owner_path, rule.sqref, rule.type, rule.operator, rule.allow_blank, rule.show_drop_down,
            rule.show_input_message, rule.show_error_message, rule.error_style, rule.ime_mode, rule.error_title,
            rule.error, rule.prompt_title, rule.prompt, rule.uid, rule.formula1, rule.formula2) == (
        "xl/worksheets/first.xml/worksheet/dataValidations/dataValidation[1]", ("A6", "B10:C10"), "whole", "between", False, True,
        False, True, "warning", "hiragana", "Bad", "No", "Hint", "Enter", "{01234567-89ab-cdef-0123-456789abcdef}", "1", "9",
    )
    assert container.rules[1].sqref == ("R104:R154", "S104:S159", "XFD104")
    assert result.worksheets[1].container is None
    with pytest.raises(FrozenInstanceError):
        rule.type = "list"


def test_preserves_explicit_zero_container_and_absent_boolean_distinctions(tmp_path):
    result = read_worksheet_native_data_validation_semantics(package(tmp_path / "zero.xlsx", sheet_one=worksheet('<dataValidations count="0"/>')))
    assert result.worksheets[0].container is not None
    assert result.worksheets[0].container.rules == ()
    assert result.worksheets[0].container.disable_prompts is None


@pytest.mark.parametrize(("xml", "expected"), [
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"><formula1>x</formula1></dataValidation></dataValidations>', ("list", None, "x", None)),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="custom"><formula1>x</formula1></dataValidation></dataValidations>', ("custom", None, "x", None)),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="none"/></dataValidations>', ("none", None, None, None)),
    ('<dataValidations count="1"><dataValidation sqref="A6"/></dataValidations>', ("none", None, None, None)),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="decimal" operator="equal"><formula1>1</formula1></dataValidation></dataValidations>', ("decimal", "equal", "1", None)),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list" operator="equal"><formula1>x</formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "list")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"><formula1> </formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "list")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="whole"><formula1>1</formula1><formula2>2</formula2></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "whole")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="whole" operator="between"><formula1>1</formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "whole")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="none"><formula1>1</formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "none")),
])
def test_formula_cardinality(tmp_path, xml, expected):
    path = package(tmp_path / "cardinality.xlsx", sheet_one=worksheet(xml))
    if expected[0] in {"list", "custom", "none", "decimal"}:
        assert (
            (lambda rule: (rule.type, rule.operator, rule.formula1, rule.formula2))(
                read_worksheet_native_data_validation_semantics(path).worksheets[0].container.rules[0]
            )
        ) == expected
    else:
        assert error(path) == expected


@pytest.mark.parametrize(("attribute", "value"), [
    ("allowBlank", "yes"), ("showDropDown", " True"), ("disablePrompts", "2"),
])
def test_rejects_non_xml_boolean_lexemes(tmp_path, attribute, value):
    container_attr = f' {attribute}="{value}"' if attribute == "disablePrompts" else ""
    rule_attr = f' {attribute}="{value}"' if attribute != "disablePrompts" else ""
    xml = f'<dataValidations count="1"{container_attr}><dataValidation sqref="A6" type="list"{rule_attr}><formula1>x</formula1></dataValidation></dataValidations>'
    assert error(package(tmp_path / f"{attribute}.xlsx", sheet_one=worksheet(xml))) == (
        "invalid-native-dv-boolean", "xl/worksheets/first.xml", attribute, value,
    )


@pytest.mark.parametrize(("sqref", "expected"), [
    ("", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "")),
    ("A:A", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "A:A")),
    ("6:6", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "6:6")),
    ("Sheet1!A6", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "Sheet1!A6")),
    ("A0", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "A0")),
    ("XFE1", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "XFE1")),
    ("A6:B5", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "A6:B5")),
    ("B6:A7", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "B6:A7")),
    ("A6 A6", ("duplicate-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "A6")),
    ("A6:A7 A7:A8", ("overlapping-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "A7:A8")),
    ("A99999999", ("invalid-native-dv-sqref", "xl/worksheets/first.xml", "sqref", "A99999999")),
])
def test_rejects_invalid_duplicate_or_overlapping_sqref(tmp_path, sqref, expected):
    xml = f'<dataValidations count="1"><dataValidation sqref="{sqref}" type="list"><formula1>x</formula1></dataValidation></dataValidations>'
    assert error(package(tmp_path / "sqref.xlsx", sheet_one=worksheet(xml))) == expected


def test_rejects_owned_tree_collisions_and_x14_at_any_depth(tmp_path):
    foreign = worksheet('<dataValidations count="0"><x:dataValidation xmlns:x="urn:bad"/></dataValidations>')
    assert error(package(tmp_path / "foreign.xlsx", sheet_one=foreign)) == (
        "owned-native-dv-namespace-collision", "xl/worksheets/first.xml", "tag", "{urn:bad}dataValidation",
    )
    x14 = worksheet('<extLst><ext><x14:dataValidations/></ext></extLst>')
    assert error(package(tmp_path / "x14.xlsx", sheet_one=x14)) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag", "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}dataValidations",
    )


def test_member_aliases_and_pathlike_are_strict(tmp_path):
    class Once:
        def __init__(self, value): self.value, self.calls = value, 0
        def __fspath__(self):
            self.calls += 1
            if self.calls > 1: raise TypeError("twice")
            return self.value
    path = Once(str(package(tmp_path / "once.xlsx")))
    assert read_worksheet_native_data_validation_semantics(path).worksheets[0].container is None
    assert path.calls == 1
    alias = package(tmp_path / "alias.xlsx", extra_members=(("xl/worksheets/%66irst.xml", worksheet()),))
    # Topology owns package graph validation and its typed collision is not
    # retyped by this adapter.
    assert error(alias) == ("duplicate-normalized-part", "xl/worksheets/first.xml", "name", "xl/worksheets/%66irst.xml")


def test_topology_failure_is_forwarded_by_identity_before_package_read(monkeypatch, tmp_path):
    sentinel = RuntimeError("topology sentinel")
    observed = []

    def fail(path):
        observed.append(path)
        raise sentinel

    monkeypatch.setattr(reader, "read_workbook_topology", fail)
    with pytest.raises(RuntimeError) as captured:
        reader.read_worksheet_native_data_validation_semantics(tmp_path / "not-opened.xlsx")
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
    (b"not-a-path", "invalid-package-path", "bytes"),
])
def test_pathlike_failures_are_typed_and_called_once(outcome, code, detail):
    value = _PathLike(outcome)
    assert error(value) == (code, f"{_PathLike.__module__}.{_PathLike.__qualname__}", "path", detail)
    assert value.calls == 1


def test_nul_path_is_typed_and_called_once():
    value = _PathLike("bad\x00path")
    assert error(value) == ("unreadable-package", "bad\x00path", "path", "embedded-nul")
    assert value.calls == 1


@pytest.mark.parametrize(("member_name", "extra_members", "expected"), [
    ("xl/worksheets/missing.xml", (), ("missing-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/%66irst.xml", (), ("noncanonical-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/%66irst.xml")),
    ("xl/worksheets/first.xml", (("xl/worksheets/%66irst.xml", worksheet()),), ("ambiguous-worksheet-member", "xl/worksheets/first.xml", "member", "xl/worksheets/first.xml")),
    ("xl/worksheets/first.xml", (("../invalid.xml", worksheet()),), ("unreadable-worksheet-part", "xl/worksheets/first.xml", "member", "invalid-member-name")),
])
def test_adapter_owns_raw_member_boundary(monkeypatch, tmp_path, member_name, extra_members, expected):
    isolated_topology(monkeypatch)
    path = package(tmp_path / "raw-member.xlsx", sheet_one_name=member_name, extra_members=extra_members)
    assert error(path) == expected


def test_adapter_types_bad_zip_before_projection(monkeypatch, tmp_path):
    isolated_topology(monkeypatch)
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip")
    assert error(path) == ("unreadable-worksheet-part", "xl/worksheets/first.xml", "xml", "BadZipFile")


@pytest.mark.parametrize(("payload", "expected"), [
    (b'<?xml version="1.0" encoding="UTF-8"<worksheet/>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-16"?><worksheet/>', ("malformed-worksheet-xml", "xl/worksheets/first.xml", "xml", "xml")),
    (b'<?xml version="1.0" encoding="unknown-encoding"?><worksheet/>', ("unsupported-xml-encoding", "xl/worksheets/first.xml", "xml", "encoding")),
    (b'<notWorksheet/>', ("invalid-worksheet-root", "xl/worksheets/first.xml", "root", "notWorksheet")),
])
def test_xml_declaration_bom_encoding_and_root_are_typed(tmp_path, payload, expected):
    assert error(package(tmp_path / "xml.xlsx", sheet_one=payload)) == expected


def test_utf16_bom_is_a_supported_xml_boundary(tmp_path):
    payload = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'.encode("utf-16")
    assert read_worksheet_native_data_validation_semantics(package(tmp_path / "utf16.xlsx", sheet_one=payload)).worksheets[0].container is None


@pytest.mark.parametrize(("attribute", "value", "field"), [
    ("count", "4294967296", "count"),
    ("count", "+00000000000", "count"),
    ("count", "0" * 5000, "count"),
    ("xWindow", "0" * 5000, "xWindow"),
    ("yWindow", "0" * 5000, "yWindow"),
])
def test_uint32_bounds_raw_lexeme_before_int(tmp_path, attribute, value, field):
    attrs = f'count="0" {attribute}="{value}"' if attribute != "count" else f'count="{value}"'
    assert error(package(tmp_path / f"{field}.xlsx", sheet_one=worksheet(f'<dataValidations {attrs}/>'))) == (
        "invalid-native-dv-uint", "xl/worksheets/first.xml", field, value,
    )


def test_uint32_accepts_xml_whitespace_plus_and_signed_zero(tmp_path):
    xml = '<dataValidations count=" +0 " xWindow="+0" yWindow=" -0 "/>'
    container = read_worksheet_native_data_validation_semantics(package(tmp_path / "uint-ok.xlsx", sheet_one=worksheet(xml))).worksheets[0].container
    assert container is not None
    assert (container.count, container.x_window, container.y_window) == (0, 0, 0)


def test_uint32_max_and_grid_boundaries_are_preserved(tmp_path):
    xml = '<dataValidations count="1" xWindow="4294967295" yWindow="4294967295"><dataValidation sqref="$A$1:$XFD$1048576" type="list"><formula1>x</formula1></dataValidation></dataValidations>'
    container = read_worksheet_native_data_validation_semantics(package(tmp_path / "limits.xlsx", sheet_one=worksheet(xml))).worksheets[0].container
    assert container is not None
    assert (container.x_window, container.y_window, container.rules[0].sqref) == (4294967295, 4294967295, ("$A$1:$XFD$1048576",))


@pytest.mark.parametrize(("kind", "operator", "formulas"), [
    ("whole", "between", "<formula1>1</formula1><formula2>2</formula2>"),
    ("decimal", "notBetween", "<formula1>1</formula1><formula2>2</formula2>"),
    ("date", "equal", "<formula1>1</formula1>"),
    ("time", "notEqual", "<formula1>1</formula1>"),
    ("textLength", "lessThan", "<formula1>1</formula1>"),
    ("whole", "lessThanOrEqual", "<formula1>1</formula1>"),
    ("whole", "greaterThan", "<formula1>1</formula1>"),
    ("whole", "greaterThanOrEqual", "<formula1>1</formula1>"),
    ("list", None, "<formula1>x</formula1>"),
    ("custom", None, "<formula1>x</formula1>"),
    ("none", None, ""),
])
def test_every_native_type_and_operator_positive(tmp_path, kind, operator, formulas):
    op = "" if operator is None else f' operator="{operator}"'
    xml = f'<dataValidations count="1"><dataValidation sqref="A6" type="{kind}"{op}>{formulas}</dataValidation></dataValidations>'
    record = read_worksheet_native_data_validation_semantics(package(tmp_path / f"{kind}.xlsx", sheet_one=worksheet(xml))).worksheets[0].container.rules[0]
    assert (record.type, record.operator) == (kind, operator)


@pytest.mark.parametrize(("attribute", "value", "field", "code"), [
    ("type", "bogus", "type", "invalid-native-dv-type"),
    ("operator", "bogus", "operator", "invalid-native-dv-operator"),
    ("errorStyle", "bogus", "errorStyle", "invalid-native-dv-error-style"),
    ("imeMode", "bogus", "imeMode", "invalid-native-dv-ime-mode"),
])
def test_invalid_enums_have_exact_tuples(tmp_path, attribute, value, field, code):
    type_value = value if attribute == "type" else "list"
    extra = "" if attribute == "type" else f' {attribute}="{value}"'
    xml = f'<dataValidations count="1"><dataValidation sqref="A6" type="{type_value}"{extra}><formula1>x</formula1></dataValidation></dataValidations>'
    assert error(package(tmp_path / f"{field}.xlsx", sheet_one=worksheet(xml))) == (code, "xl/worksheets/first.xml", field, value)


@pytest.mark.parametrize("ime", ["noControl", "off", "on", "disabled", "hiragana", "fullKatakana", "halfKatakana", "fullAlpha", "halfAlpha", "fullHangul", "halfHangul"])
def test_every_ime_mode_is_preserved(tmp_path, ime):
    xml = f'<dataValidations count="1"><dataValidation sqref="A6" type="list" imeMode="{ime}"><formula1>x</formula1></dataValidation></dataValidations>'
    assert read_worksheet_native_data_validation_semantics(package(tmp_path / f"{ime}.xlsx", sheet_one=worksheet(xml))).worksheets[0].container.rules[0].ime_mode == ime


@pytest.mark.parametrize("style", ["stop", "warning", "information"])
def test_every_error_style_is_preserved(tmp_path, style):
    xml = f'<dataValidations count="1"><dataValidation sqref="A6" type="list" errorStyle="{style}"><formula1>x</formula1></dataValidation></dataValidations>'
    assert read_worksheet_native_data_validation_semantics(package(tmp_path / f"{style}.xlsx", sheet_one=worksheet(xml))).worksheets[0].container.rules[0].error_style == style


@pytest.mark.parametrize(("attribute", "value", "expected"), [
    ("allowBlank", "0", False), ("allowBlank", "1", True),
    ("showDropDown", "false", False), ("showDropDown", "true", True),
    ("showInputMessage", "0", False), ("showInputMessage", "1", True),
    ("showErrorMessage", "false", False), ("showErrorMessage", "true", True),
])
def test_rule_boolean_tri_state_preserves_without_inversion(tmp_path, attribute, value, expected):
    xml = f'<dataValidations count="1"><dataValidation sqref="A6" type="list" {attribute}="{value}"><formula1>x</formula1></dataValidation></dataValidations>'
    rule = read_worksheet_native_data_validation_semantics(package(tmp_path / f"{attribute}-{value}.xlsx", sheet_one=worksheet(xml))).worksheets[0].container.rules[0]
    assert getattr(rule, {"allowBlank": "allow_blank", "showDropDown": "show_drop_down", "showInputMessage": "show_input_message", "showErrorMessage": "show_error_message"}[attribute]) is expected


@pytest.mark.parametrize(("xml", "expected"), [
    ('<dataValidations count="0"/><dataValidations count="0"/>', ("duplicate-native-dv-container", "xl/worksheets/first.xml", "dataValidations", "")),
    ('<dataValidation sqref="A6"/>', ("invalid-owned-native-dv-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}dataValidation")),
    ('<ext xmlns="urn:ext"><formula1 xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">x</formula1></ext>', ("invalid-owned-native-dv-parent", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}formula1")),
    ('<dataValidations count="0" extra="x"/>', ("unknown-native-dv-attribute", "xl/worksheets/first.xml", "attribute", "extra")),
    ('<dataValidations count="0"><bad/></dataValidations>', ("invalid-native-dv-container-child", "xl/worksheets/first.xml", "tag", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}bad")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="none" extra="x"/></dataValidations>', ("unknown-native-dv-attribute", "xl/worksheets/first.xml", "attribute", "extra")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="none"><formula1>x</formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "none")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"><formula1>x</formula1><formula1>y</formula1></dataValidation></dataValidations>', ("duplicate-native-dv-child", "xl/worksheets/first.xml", "formula1", "")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"><formula2>x</formula2><formula1>y</formula1></dataValidation></dataValidations>', ("invalid-native-dv-child-order", "xl/worksheets/first.xml", "tag", "formula2")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"><formula1 extra="x">x</formula1></dataValidation></dataValidations>', ("unknown-native-dv-attribute", "xl/worksheets/first.xml", "attribute", "extra")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"><formula1><x/></formula1></dataValidation></dataValidations>', ("invalid-native-dv-content", "xl/worksheets/first.xml", "formula1", "nested")),
    ('text<dataValidations count="0"/>', ("invalid-native-dv-content", "xl/worksheets/first.xml", "worksheet", "text")),
    ('<dataValidations count="0"/>tail', ("invalid-native-dv-content", "xl/worksheets/first.xml", "worksheet", "tail")),
    ('<dataValidations count="0">text</dataValidations>', ("invalid-native-dv-content", "xl/worksheets/first.xml", "dataValidations", "text")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="none">text</dataValidation></dataValidations>', ("invalid-native-dv-content", "xl/worksheets/first.xml", "dataValidation", "text")),
])
def test_owned_tree_faults_have_exact_tuples(tmp_path, xml, expected):
    assert error(package(tmp_path / "owned.xlsx", sheet_one=worksheet(xml))) == expected


def test_foreign_lookalike_only_fails_when_it_can_masquerade(tmp_path):
    safe = worksheet('<ext xmlns="urn:ext"><dataValidations count="0"/></ext>')
    assert read_worksheet_native_data_validation_semantics(package(tmp_path / "foreign-safe.xlsx", sheet_one=safe)).worksheets[0].container is None
    dangerous = worksheet('<dataValidations count="0"><x:dataValidation xmlns:x="urn:foreign"/></dataValidations>')
    assert error(package(tmp_path / "foreign-dangerous.xlsx", sheet_one=dangerous)) == (
        "owned-native-dv-namespace-collision", "xl/worksheets/first.xml", "tag", "{urn:foreign}dataValidation",
    )


@pytest.mark.parametrize("nested", [
    '<x14:dataValidations/>',
    '<ext><x14:dataValidations/></ext>',
    '<ext><deep><x14:dataValidations/></deep></ext>',
    '<dataValidations count="0"><x14:dataValidations/></dataValidations>',
])
def test_x14_at_every_depth_precedes_native_tree_failures(tmp_path, nested):
    assert error(package(tmp_path / "x14-depth.xlsx", sheet_one=worksheet(nested))) == (
        "unsupported_x14_content", "xl/worksheets/first.xml", "tag", "{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}dataValidations",
    )


@pytest.mark.parametrize(("uid", "expected"), [
    ("{01234567-89ab-cdef-0123-456789abcdef}", None),
    ("01234567-89ab-cdef-0123-456789abcdef", ("invalid-native-dv-uid", "xl/worksheets/first.xml", "uid", "01234567-89ab-cdef-0123-456789abcdef")),
])
def test_braced_xr_uid_is_preserved_or_typed(tmp_path, uid, expected):
    xml = f'<dataValidations count="1"><dataValidation sqref="A6" type="list" xr:uid="{uid}"><formula1>x</formula1></dataValidation></dataValidations>'
    path = package(tmp_path / "uid.xlsx", sheet_one=worksheet(xml))
    if expected is None:
        assert read_worksheet_native_data_validation_semantics(path).worksheets[0].container.rules[0].uid == uid
    else:
        assert error(path) == expected


def test_full_two_sheet_projection_default_zero_populated_and_all_records_frozen(tmp_path):
    first = worksheet('<dataValidations count="0"/>')
    second = worksheet(
        '<dataValidations count="1" disablePrompts="true" xWindow="1" yWindow="2">'
        '<dataValidation sqref="A6 B10:C10 R104:R154 S104:S159 XFD104" type="list" allowBlank="false" showDropDown="true" showInputMessage="false" showErrorMessage="true" errorStyle="stop" imeMode="on" errorTitle="E" error="e" promptTitle="P" prompt="p"><formula1>Sheet1!$A$1:$A$2</formula1></dataValidation>'
        '</dataValidations>'
    )
    result = read_worksheet_native_data_validation_semantics(package(tmp_path / "projection.xlsx", sheet_one=first, sheet_two=second))
    assert [(item.worksheet.name, item.container is None if item.container is None else item.container.count) for item in result.worksheets] == [("Первый", 0), ("Второй", 1)]
    container = result.worksheets[1].container
    assert container is not None
    rule = container.rules[0]
    assert (container.disable_prompts, container.x_window, container.y_window, rule.sqref, rule.formula1) == (
        True, 1, 2, ("A6", "B10:C10", "R104:R154", "S104:S159", "XFD104"), "Sheet1!$A$1:$A$2",
    )
    with pytest.raises(FrozenInstanceError): result.worksheets = ()
    with pytest.raises(FrozenInstanceError): result.worksheets[0].container = None
    with pytest.raises(FrozenInstanceError): container.count = 2
    with pytest.raises(FrozenInstanceError): rule.formula1 = "changed"
