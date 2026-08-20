from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import rns_import_server.opc_worksheet_native_dv_reader as reader
from rns_import_server.opc_worksheet_native_dv_reader import (
    OPCWorksheetNativeDvReaderError,
    read_worksheet_native_data_validation_semantics,
)
from rns_import_server.opc_workbook_topology import OPCWorkbookTopologyError
from tests.opc_worksheet_native_dv_fixture_factory import package, worksheet


def error(path):
    with pytest.raises((OPCWorksheetNativeDvReaderError, OPCWorkbookTopologyError)) as captured:
        read_worksheet_native_data_validation_semantics(path)
    return captured.value.as_tuple()


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
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"><formula1>x</formula1></dataValidation></dataValidations>', None),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="custom"><formula1>x</formula1></dataValidation></dataValidations>', None),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="none"/></dataValidations>', None),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="decimal" operator="equal"><formula1>1</formula1></dataValidation></dataValidations>', None),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="whole"><formula1>1</formula1><formula2>2</formula2></dataValidation></dataValidations>', None),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list" operator="equal"><formula1>x</formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "list")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="whole" operator="between"><formula1>1</formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "whole")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="none"><formula1>1</formula1></dataValidation></dataValidations>', ("invalid-native-dv-formula-cardinality", "xl/worksheets/first.xml", "formula", "none")),
])
def test_formula_cardinality(tmp_path, xml, expected):
    path = package(tmp_path / "cardinality.xlsx", sheet_one=worksheet(xml))
    if expected is None:
        assert read_worksheet_native_data_validation_semantics(path).worksheets[0].container is not None
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


@pytest.mark.parametrize("sqref", ["", "A:A", "6:6", "Sheet1!A6", "A0", "XFE1", "A6:B5", "B6:A7", "A6 A6", "A6:A7 A7:A8", "A99999999"])
def test_rejects_invalid_duplicate_or_overlapping_sqref(tmp_path, sqref):
    xml = f'<dataValidations count="1"><dataValidation sqref="{sqref}" type="list"><formula1>x</formula1></dataValidation></dataValidations>'
    result = error(package(tmp_path / "sqref.xlsx", sheet_one=worksheet(xml)))
    assert result[0] in {"invalid-native-dv-sqref", "overlapping-native-dv-sqref"}


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
