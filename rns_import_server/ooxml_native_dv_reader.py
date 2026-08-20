"""Strict native (2006) SpreadsheetML data-validation reader."""
from __future__ import annotations

from dataclasses import dataclass
import re
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
X14_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
MAX_ROW, MAX_COLUMN, UINT32_MAX = 1_048_576, 16_384, 4_294_967_295
_GUID = re.compile(r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$")
_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)$")
_RANGE = re.compile(r"^(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*)(?::(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*))?$")
_TYPES = frozenset(("none", "whole", "decimal", "list", "date", "time", "textLength", "custom"))
_OPERATORS = frozenset(("between", "notBetween", "equal", "notEqual", "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual"))
_ERROR_STYLES = frozenset(("stop", "warning", "information"))
_IME_MODES = frozenset(("noControl", "off", "on", "disabled", "hiragana", "fullKatakana", "halfKatakana", "fullAlpha", "halfAlpha", "fullHangul", "halfHangul"))
_COMPARISON_TYPES = frozenset(("whole", "decimal", "date", "time", "textLength"))
_CONTAINER_ATTRS = frozenset(("count", "disablePrompts", "xWindow", "yWindow"))
_RULE_ATTRS = frozenset(("type", "errorStyle", "imeMode", "operator", "allowBlank", "showDropDown", "showInputMessage", "showErrorMessage", "errorTitle", "error", "promptTitle", "prompt", "sqref", f"{{{XR_NS}}}uid"))


class NativeDvParseError(ValueError):
    """One deterministic, user-actionable native-DV parsing fault."""

    def __init__(self, code: str, owner_path: str, detail: str = "") -> None:
        self.code, self.owner_path, self.detail = code, owner_path, detail
        super().__init__(f"{code} at {owner_path}" + (f": {detail}" if detail else ""))


@dataclass(frozen=True, slots=True)
class NativeDataValidation:
    owner_path: str
    sqref: tuple[str, ...]
    type: str
    operator: str | None
    allow_blank: bool | None
    show_drop_down: bool | None
    show_input_message: bool | None
    show_error_message: bool | None
    error_style: str | None
    ime_mode: str | None
    error_title: str | None
    error: str | None
    prompt_title: str | None
    prompt: str | None
    uid: str | None
    formula1: str | None
    formula2: str | None


@dataclass(frozen=True, slots=True)
class NativeDataValidations:
    owner_path: str
    count: int
    disable_prompts: bool | None
    x_window: int | None
    y_window: int | None
    rules: tuple[NativeDataValidation, ...]


@dataclass(frozen=True, slots=True)
class NativeDvReadResult:
    worksheet_part: str
    container: NativeDataValidations | None

    @property
    def data_validations(self) -> NativeDataValidations | None:
        return self.container

    @property
    def rules(self) -> tuple[NativeDataValidation, ...]:
        return () if self.container is None else self.container.rules


def _q(name: str) -> str:
    return f"{{{MAIN_NS}}}{name}"


def _main(element: ET.Element, name: str) -> bool:
    return element.tag == _q(name)


def _path(part: str, suffix: str) -> str:
    return f"{part}#worksheet/{suffix}"


def _fail(code: str, path: str, detail: str = "") -> None:
    raise NativeDvParseError(code, path, detail)


def _attrs(element: ET.Element, allowed: frozenset[str], path: str) -> None:
    for key in element.attrib:
        if key not in allowed:
            _fail("unknown_attribute", path, key)


def _mixed(element: ET.Element, path: str) -> None:
    if element.text and element.text.strip():
        _fail("mixed_content", path, "text")
    for child in element:
        if child.tail and child.tail.strip():
            _fail("mixed_content", path, "tail")


def _required(attributes: dict[str, str], key: str, path: str) -> str:
    value = attributes.get(key)
    if value is None or not value.strip():
        _fail("missing_required_attribute", path, key)
    return value


def _bool(value: str | None, path: str, key: str) -> bool | None:
    if value is None:
        return None
    if value in ("1", "true"):
        return True
    if value in ("0", "false"):
        return False
    _fail("invalid_boolean", path, key)


def _collapse_xml_whitespace(value: str) -> str:
    return re.sub(r"[\x09\x0A\x0D\x20]+", " ", value).strip(" ")


def _u32(value: str | None, path: str, key: str) -> int | None:
    if value is None:
        return None
    lexical = _collapse_xml_whitespace(value)
    if not re.fullmatch(r"(?:\+?[0-9]+|-0+)", lexical):
        _fail("invalid_integer", path, key)
    result = int(lexical)
    if result > UINT32_MAX:
        _fail("integer_out_of_range", path, key)
    return result


def _enum(value: str | None, choices: frozenset[str], path: str, key: str) -> str | None:
    if value is not None and value not in choices:
        _fail("invalid_enum", path, key)
    return value


def _column(value: str) -> int:
    number = 0
    for character in value.upper():
        number = number * 26 + ord(character) - 64
    return number


def _coordinates(value: str, path: str) -> tuple[int, int]:
    match = _CELL.fullmatch(value)
    if match is None:
        _fail("malformed_sqref", path, value)
    column, row = _column(match.group(1)), int(match.group(2))
    if column > MAX_COLUMN or row > MAX_ROW:
        _fail("sqref_out_of_bounds", path, value)
    return row, column


def _sqref(value: str | None, path: str) -> tuple[str, ...]:
    if value is None or not value.strip():
        _fail("missing_sqref", path)
    collapsed = _collapse_xml_whitespace(value)
    if not collapsed:
        _fail("missing_sqref", path)
    result = tuple(collapsed.split(" "))
    boxes: list[tuple[int, int, int, int]] = []
    seen: set[str] = set()
    for token in result:
        match = _RANGE.fullmatch(token)
        if match is None:
            _fail("malformed_sqref", path, token)
        start_row, start_column = _coordinates(match.group(1), path)
        end_row, end_column = (start_row, start_column) if match.group(2) is None else _coordinates(match.group(2), path)
        if end_row < start_row or end_column < start_column:
            _fail("reversed_sqref", path, token)
        if token in seen:
            _fail("duplicate_sqref", path, token)
        for top, left, bottom, right in boxes:
            if not (end_row < top or bottom < start_row or end_column < left or right < start_column):
                _fail("overlapping_sqref", path, token)
        seen.add(token)
        boxes.append((start_row, start_column, end_row, end_column))
    return result


def _uid(value: str | None, path: str) -> str | None:
    if value is not None and not _GUID.fullmatch(value):
        _fail("invalid_uid", path, value)
    return value


def _formula(element: ET.Element, path: str) -> str:
    _attrs(element, frozenset(), path)
    if list(element) or element.text is None or not element.text.strip():
        _fail("invalid_formula", path)
    return element.text


def _rule(element: ET.Element, path: str) -> NativeDataValidation:
    _attrs(element, _RULE_ATTRS, path)
    _mixed(element, path)
    validation_type = element.attrib.get("type", "none")
    _enum(validation_type, _TYPES, path, "type")
    operator = _enum(element.attrib.get("operator"), _OPERATORS, path, "operator")
    error_style = _enum(element.attrib.get("errorStyle"), _ERROR_STYLES, path, "errorStyle")
    ime_mode = _enum(element.attrib.get("imeMode"), _IME_MODES, path, "imeMode")
    formula1: str | None = None
    formula2: str | None = None
    state = 0
    for child in element:
        if _main(child, "formula1"):
            if formula1 is not None:
                _fail("invalid_formula_cardinality", path, "formula1")
            if state != 0:
                _fail("invalid_child_order", path, "formula1")
            formula1 = _formula(child, f"{path}/formula1[1]")
            state = 1
        elif _main(child, "formula2"):
            if formula2 is not None:
                _fail("invalid_formula_cardinality", path, "formula2")
            if state != 1:
                _fail("invalid_child_order", path, "formula2")
            formula2 = _formula(child, f"{path}/formula2[1]")
            state = 2
        else:
            _fail("unknown_owned_content", path, str(child.tag))
    if operator is not None:
        if validation_type not in _COMPARISON_TYPES:
            _fail("invalid_operator_for_type", path, "operator")
        if operator in ("between", "notBetween"):
            if formula1 is None or formula2 is None:
                _fail("invalid_formula_cardinality", path, "comparison range")
        elif formula1 is None or formula2 is not None:
            _fail("invalid_formula_cardinality", path, "comparison")
    elif validation_type in ("list", "custom"):
        if formula1 is None or formula2 is not None:
            _fail("invalid_formula_cardinality", path, validation_type)
    elif validation_type == "none":
        if formula1 is not None or formula2 is not None:
            _fail("invalid_formula_cardinality", path, "none")
    elif formula1 is not None or formula2 is not None:
        _fail("invalid_formula_cardinality", path, "operator required")
    return NativeDataValidation(
        path, _sqref(_required(element.attrib, "sqref", path), path), validation_type, operator,
        _bool(element.attrib.get("allowBlank"), path, "allowBlank"),
        _bool(element.attrib.get("showDropDown"), path, "showDropDown"),
        _bool(element.attrib.get("showInputMessage"), path, "showInputMessage"),
        _bool(element.attrib.get("showErrorMessage"), path, "showErrorMessage"),
        error_style, ime_mode, element.attrib.get("errorTitle"), element.attrib.get("error"),
        element.attrib.get("promptTitle"), element.attrib.get("prompt"),
        _uid(element.attrib.get(f"{{{XR_NS}}}uid"), path), formula1, formula2,
    )


def _container(element: ET.Element, path: str) -> NativeDataValidations:
    _attrs(element, _CONTAINER_ATTRS, path)
    _mixed(element, path)
    count = _u32(_required(element.attrib, "count", path), path, "count")
    assert count is not None
    rules: list[NativeDataValidation] = []
    for child in element:
        if not _main(child, "dataValidation"):
            _fail("unknown_owned_content", path, str(child.tag))
        rules.append(_rule(child, f"{path}/dataValidation[{len(rules) + 1}]"))
    if count != len(rules):
        _fail("count_mismatch", path, f"count={count}, rules={len(rules)}")
    return NativeDataValidations(
        path, count, _bool(element.attrib.get("disablePrompts"), path, "disablePrompts"),
        _u32(element.attrib.get("xWindow"), path, "xWindow"),
        _u32(element.attrib.get("yWindow"), path, "yWindow"), tuple(rules),
    )


def read_native_data_validations(worksheet_part: str, worksheet_xml: str | bytes) -> NativeDvReadResult:
    if not isinstance(worksheet_part, str) or not worksheet_part or worksheet_part.strip() != worksheet_part:
        _fail("invalid_worksheet_part", str(worksheet_part), "worksheet_part")
    root_path = _path(worksheet_part, "")
    if not isinstance(worksheet_xml, (str, bytes)):
        _fail("invalid_worksheet_xml", root_path)
    try:
        root = ET.fromstring(worksheet_xml)
    except (ET.ParseError, UnicodeError) as exc:
        _fail("invalid_xml", root_path, str(exc))
    if not _main(root, "worksheet"):
        _fail("invalid_worksheet_root", root_path)
    containers = [child for child in root if _main(child, "dataValidations")]
    if len(containers) > 1:
        _fail("multiple_data_validations", root_path)
    for child in root:
        if child.tag == f"{{{X14_NS}}}dataValidations":
            _fail("unsupported_x14_content", root_path, str(child.tag))
    if not containers:
        return NativeDvReadResult(worksheet_part, None)
    return NativeDvReadResult(worksheet_part, _container(containers[0], _path(worksheet_part, "dataValidations[1]")))


parse_native_data_validations = read_native_data_validations
read_native_dv = read_native_data_validations

__all__ = [
    "MAIN_NS", "XR_NS", "X14_NS", "MAX_ROW", "MAX_COLUMN", "UINT32_MAX", "NativeDvParseError",
    "NativeDataValidation", "NativeDataValidations", "NativeDvReadResult",
    "read_native_data_validations", "parse_native_data_validations", "read_native_dv",
]
