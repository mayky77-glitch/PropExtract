from dataclasses import FrozenInstanceError

import pytest

from rns_import_server.ooxml_native_dv_reader import (
    MAIN_NS,
    XR_NS,
    X14_NS,
    UINT32_MAX,
    NativeDvParseError,
    read_native_data_validations,
)


def _ws(content: str) -> str:
    return f'<worksheet xmlns="{MAIN_NS}" xmlns:xr="{XR_NS}">{content}</worksheet>'


def _rule(attributes: str, children: str = "") -> str:
    return f"<dataValidation {attributes}>{children}</dataValidation>"


def _read(content: str, part: str = "xl/worksheets/sheet1.xml"):
    return read_native_data_validations(part, _ws(content))


def test_complete_ordered_native_container_preserves_two_parts_and_grid_boundaries():
    xml = '<dataValidations count="2" disablePrompts="false" xWindow=" +0006 " yWindow="104">' + _rule(
        'sqref="A6 B10:C10" type="whole" operator="between" allowBlank="true" showDropDown="false" showInputMessage="1" showErrorMessage="0" errorStyle="warning" imeMode="fullKatakana" errorTitle="Bad" error="No" promptTitle="Hint" prompt="Choose" xr:uid="{01234567-89AB-CDEF-0123-456789ABCDEF}"',
        '<formula1>1</formula1><formula2>10</formula2>',
    ) + _rule('sqref="$XFD$104:$XFD$104" type="list"', '<formula1>"A,B"</formula1>') + '</dataValidations>'
    result = _read(xml, "xl/worksheets/dashboard.xml")
    assert result.worksheet_part == "xl/worksheets/dashboard.xml"
    assert result.container is not None
    assert (result.container.count, result.container.disable_prompts, result.container.x_window, result.container.y_window) == (2, False, 6, 104)
    first, second = result.rules
    assert first.sqref == ("A6", "B10:C10")
    assert (first.type, first.operator, first.allow_blank, first.show_drop_down, first.show_input_message, first.show_error_message) == ("whole", "between", True, False, True, False)
    assert (first.error_style, first.ime_mode, first.error_title, first.error, first.prompt_title, first.prompt, first.uid, first.formula1, first.formula2) == ("warning", "fullKatakana", "Bad", "No", "Hint", "Choose", "{01234567-89AB-CDEF-0123-456789ABCDEF}", "1", "10")
    assert (second.sqref, second.type, second.formula1, second.formula2) == (("$XFD$104:$XFD$104",), "list", '"A,B"', None)
    with pytest.raises(FrozenInstanceError):
        first.type = "list"  # type: ignore[misc]


def test_absent_and_explicit_boolean_values_remain_tri_state():
    for value, expected in ((None, None), ("false", False), ("true", True)):
        attributes = 'sqref="A6"' if value is None else f'sqref="A6" allowBlank="{value}" showDropDown="{value}" showInputMessage="{value}" showErrorMessage="{value}"'
        rule = _read(f'<dataValidations count="1">{_rule(attributes)}</dataValidations>').rules[0]
        assert (rule.allow_blank, rule.show_drop_down, rule.show_input_message, rule.show_error_message) == (expected,) * 4
        container = _read(f'<dataValidations count="0" disablePrompts="{value or "false"}"/>').container
        assert container is not None
        assert container.disable_prompts is (False if value is None else expected)


@pytest.mark.parametrize("validation_type", ("none", "whole", "decimal", "list", "date", "time", "textLength", "custom"))
def test_all_validation_types(validation_type: str):
    if validation_type == "none":
        child, attrs = "", ""
    elif validation_type in ("list", "custom"):
        child, attrs = "<formula1>x</formula1>", ""
    else:
        child, attrs = "<formula1>1</formula1>", ' operator="equal"'
    result = _read(f'<dataValidations count="1">{_rule(f"sqref=\"A6\" type=\"{validation_type}\"{attrs}", child)}</dataValidations>')
    assert result.rules[0].type == validation_type


@pytest.mark.parametrize("value", ("between", "notBetween", "equal", "notEqual", "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual"))
def test_all_comparison_operators(value: str):
    formulas = "<formula1>1</formula1><formula2>2</formula2>" if value in ("between", "notBetween") else "<formula1>1</formula1>"
    rule = _read(f'<dataValidations count="1">{_rule(f"sqref=\"A10\" type=\"decimal\" operator=\"{value}\"", formulas)}</dataValidations>').rules[0]
    assert rule.operator == value


@pytest.mark.parametrize("attribute,value", (("errorStyle", "stop"), ("errorStyle", "warning"), ("errorStyle", "information"), ("imeMode", "noControl"), ("imeMode", "off"), ("imeMode", "on"), ("imeMode", "disabled"), ("imeMode", "hiragana"), ("imeMode", "fullKatakana"), ("imeMode", "halfKatakana"), ("imeMode", "fullAlpha"), ("imeMode", "halfAlpha"), ("imeMode", "fullHangul"), ("imeMode", "halfHangul")))
def test_all_error_style_and_ime_mode_enums(attribute: str, value: str):
    rule = _read(f'<dataValidations count="1">{_rule(f"sqref=\"A104\" {attribute}=\"{value}\"")}</dataValidations>').rules[0]
    assert getattr(rule, "error_style" if attribute == "errorStyle" else "ime_mode") == value


def test_zero_rule_container_and_absent_container_are_distinct():
    empty = _read('<dataValidations count="0"/>')
    absent = _read('')
    assert empty.container is not None and empty.container.rules == ()
    assert absent.container is None and absent.rules == ()


@pytest.mark.parametrize(("value", "expected"), (("2147483648", 2147483648), (str(UINT32_MAX), UINT32_MAX), (f"+{UINT32_MAX}", UINT32_MAX), (" -000 ", 0)))
def test_unsigned_integer_xml_whitespace_and_boundaries(value: str, expected: int):
    container = _read(f'<dataValidations count="0" xWindow="{value}" yWindow="{value}"/>').container
    assert container is not None and (container.x_window, container.y_window) == (expected, expected)


@pytest.mark.parametrize(("xml", "expected"), (
    ('<dataValidations count="1"/>', ("count_mismatch", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]", "count=1, rules=0")),
    ('<dataValidations count="0" bogus="x"/>', ("unknown_attribute", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]", "bogus")),
    ('<dataValidations count="0" disablePrompts="yes"/>', ("invalid_boolean", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]", "disablePrompts")),
    ('<dataValidations count="-1"/>', ("invalid_integer", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]", "count")),
    (f'<dataValidations count="0" xWindow="{UINT32_MAX + 1}"/>', ("integer_out_of_range", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]", "xWindow")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="bad"/></dataValidations>', ("invalid_enum", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "type")),
    ('<dataValidations count="1"><dataValidation sqref="A6" xr:uid="bad"/></dataValidations>', ("invalid_uid", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "bad")),
    ('<dataValidations count="1"><dataValidation sqref="A0"/></dataValidations>', ("malformed_sqref", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "A0")),
    ('<dataValidations count="1"><dataValidation sqref="A6 A6"/></dataValidations>', ("duplicate_sqref", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "A6")),
    ('<dataValidations count="1"><dataValidation sqref="A6:B7 B7:C8"/></dataValidations>', ("overlapping_sqref", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "B7:C8")),
    ('<dataValidations count="1"><dataValidation sqref="B7:A6"/></dataValidations>', ("reversed_sqref", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "B7:A6")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list"/></dataValidations>', ("invalid_formula_cardinality", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "list")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="whole" operator="between"><formula1>1</formula1></dataValidation></dataValidations>', ("invalid_formula_cardinality", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "comparison range")),
    ('<dataValidations count="1"><dataValidation sqref="A6" type="list" operator="equal"><formula1>1</formula1></dataValidation></dataValidations>', ("invalid_operator_for_type", "xl/worksheets/sheet1.xml#worksheet/dataValidations[1]/dataValidation[1]", "operator")),
))
def test_exact_typed_fault_tuples(xml: str, expected: tuple[str, str, str]):
    with pytest.raises(NativeDvParseError) as error:
        _read(xml)
    assert (error.value.code, error.value.owner_path, error.value.detail) == expected


@pytest.mark.parametrize(("content", "code"), (
    ('<dataValidations count="0"/><dataValidations count="0"/>', "multiple_data_validations"),
    ('<dataValidations count="1"><dataValidation sqref="A6"><formula2>1</formula2></dataValidation></dataValidations>', "invalid_child_order"),
    ('<dataValidations count="1"><dataValidation sqref="A6"><formula1>1</formula1><formula1>2</formula1></dataValidation></dataValidations>', "invalid_formula_cardinality"),
    ('<dataValidations count="1">noise<dataValidation sqref="A6"/></dataValidations>', "mixed_content"),
    ('<dataValidations count="1"><dataValidation sqref="A6">noise</dataValidation></dataValidations>', "mixed_content"),
    ('<dataValidations count="1"><x14:dataValidation xmlns:x14="urn:x14" sqref="A6"/></dataValidations>', "unknown_owned_content"),
    (f'<x14:dataValidations xmlns:x14="{X14_NS}"/>', "unsupported_x14_content"),
))
def test_owned_content_and_x14_fail_closed(content: str, code: str):
    with pytest.raises(NativeDvParseError) as error:
        _read(content)
    assert error.value.code == code


def test_nested_x14_data_validations_fail_at_worksheet_boundary_but_unrelated_extensions_are_ignored():
    nested = f'<extLst><ext uri="{{test}}"><x14:dataValidations xmlns:x14="{X14_NS}"/></ext></extLst>'
    with pytest.raises(NativeDvParseError) as error:
        _read(nested)
    assert (error.value.code, error.value.owner_path, error.value.detail) == (
        "unsupported_x14_content",
        "xl/worksheets/sheet1.xml#worksheet/",
        f"{{{X14_NS}}}dataValidations",
    )
    assert _read('<extLst><ext uri="{unrelated}"/></extLst>').container is None


def test_unknown_xml_bytes_encoding_is_typed_boundary_fault():
    xml = b"<?xml version='1.0' encoding='BOGUS'?><worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'/>"
    with pytest.raises(NativeDvParseError) as error:
        read_native_data_validations("xl/worksheets/sheet1.xml", xml)
    assert (error.value.code, error.value.owner_path, error.value.detail) == (
        "invalid_xml",
        "xl/worksheets/sheet1.xml#worksheet/",
        "unsupported encoding",
    )


@pytest.mark.parametrize("xml", ("<worksheet>", '<notWorksheet xmlns="%s"/>' % MAIN_NS))
def test_xml_and_root_faults(xml: str):
    with pytest.raises(NativeDvParseError) as error:
        read_native_data_validations("xl/worksheets/sheet1.xml", xml)
    assert error.value.code in ("invalid_xml", "invalid_worksheet_root")
