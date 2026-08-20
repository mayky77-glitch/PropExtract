"""Strict, immutable native SpreadsheetML data-validation semantics."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology


_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_X14: Final = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
_XR: Final = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
_WORKSHEET: Final = f"{{{_SML}}}worksheet"
_CONTAINER: Final = f"{{{_SML}}}dataValidations"
_RULE: Final = f"{{{_SML}}}dataValidation"
_FORMULA1: Final = f"{{{_SML}}}formula1"
_FORMULA2: Final = f"{{{_SML}}}formula2"
_X14_CONTAINER: Final = f"{{{_X14}}}dataValidations"
_XML_DECLARATION: Final = re.compile(
    br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']', re.IGNORECASE
)
_XML_WHITESPACE: Final = " \t\r\n"
_UINT_LEXEME: Final = re.compile(r"(?:\+?[0-9]+|-[0]+)\Z")
_CELL: Final = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})\Z")
_GUID: Final = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}\Z")
_BOOLEANS: Final = {"0": False, "1": True, "false": False, "true": True}
_TYPES: Final = frozenset({"none", "whole", "decimal", "list", "date", "time", "textLength", "custom"})
_OPERATORS: Final = frozenset({"between", "notBetween", "equal", "notEqual", "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual"})
_RANGE_OPERATORS: Final = frozenset({"between", "notBetween"})
_ERROR_STYLES: Final = frozenset({"stop", "warning", "information"})
_IME_MODES: Final = frozenset({"noControl", "off", "on", "disabled", "hiragana", "fullKatakana", "halfKatakana", "fullAlpha", "halfAlpha", "fullHangul", "halfHangul"})
_MAX_UINT: Final = 4_294_967_295
_MAX_ROW: Final = 1_048_576
_MAX_COLUMN: Final = 16_384
_COMPARISON_TYPES: Final = frozenset({"whole", "decimal", "date", "time", "textLength"})


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class NativeDataValidations:
    owner_path: str
    count: int
    disable_prompts: bool | None
    x_window: int | None
    y_window: int | None
    rules: tuple[NativeDataValidation, ...]


@dataclass(frozen=True)
class WorksheetNativeDvSemantics:
    worksheet: WorksheetDescriptor
    container: NativeDataValidations | None


@dataclass(frozen=True)
class WorkbookNativeDvSemantics:
    worksheets: tuple[WorksheetNativeDvSemantics, ...]


@dataclass
class OPCWorksheetNativeDvReaderError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetNativeDvReaderError(code, subject, field, detail)


def _coerce_package_path(value: os.PathLike[str] | str) -> str:
    subject = f"{type(value).__module__}.{type(value).__qualname__}"
    try:
        path = os.fspath(value)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except (ValueError, OSError) as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str):
        _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path:
        _fail("unreadable-package", path, "path", "embedded-nul")
    return path


def _member(path: str, part: CanonicalPartURI) -> bytes:
    """Read exactly the topology-owned, canonical ZIP member."""
    try:
        with ZipFile(path) as archive:
            matches = []
            for info in archive.infolist():
                try:
                    canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError:
                    _fail("unreadable-worksheet-part", part.value, "member", "invalid-member-name")
                if canonical == part:
                    matches.append(info)
            if not matches:
                _fail("missing-worksheet-member", part.value, "member", part.value)
            if len(matches) != 1:
                _fail("ambiguous-worksheet-member", part.value, "member", part.value)
            info = matches[0]
            if info.filename != part.value:
                _fail("noncanonical-worksheet-member", part.value, "member", info.filename)
            return archive.read(info)
    except OPCWorksheetNativeDvReaderError:
        raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error:
        _fail("unreadable-worksheet-part", part.value, "xml", type(error).__name__)
    raise AssertionError("unreachable")


def _xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    declaration = _XML_DECLARATION.match(candidate)
    if declaration is not None:
        try:
            declaration.group(1).decode("ascii").lower().replace("_", "-")
            ET.fromstring(payload)
        except (LookupError, UnicodeError, ValueError):
            _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    try:
        root = ET.fromstring(payload)
    except LookupError:
        _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except (ET.ParseError, UnicodeError, ValueError):
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    if root.tag != _WORKSHEET:
        _fail("invalid-worksheet-root", part.value, "root", str(root.tag))
    return root


def _nonwhite(value: str | None) -> bool:
    return bool(value and not value.isspace())


def _mixed(element: ET.Element, part: str, field: str) -> None:
    if _nonwhite(element.text):
        _fail("invalid-native-dv-content", part, field, "text")
    for child in element:
        if _nonwhite(child.tail):
            _fail("invalid-native-dv-content", part, field, "tail")


def _uint32(value: str | None, part: str, field: str) -> int:
    text = "" if value is None else value
    lexical = text.strip(_XML_WHITESPACE)
    if _UINT_LEXEME.fullmatch(lexical) is None:
        _fail("invalid-native-dv-uint", part, field, text)
    digits = lexical.lstrip("+-").lstrip("0") or "0"
    if len(digits) > 10 or (len(digits) == 10 and digits > "4294967295"):
        _fail("invalid-native-dv-uint", part, field, text)
    return int(lexical)


def _boolean(value: str, part: str, field: str) -> bool:
    result = _BOOLEANS.get(value)
    if result is None and value not in _BOOLEANS:
        _fail("invalid-native-dv-boolean", part, field, value)
    return result


def _a1_endpoint(value: str, part: str, sqref: str) -> tuple[int, int]:
    match = _CELL.fullmatch(value)
    if match is None:
        _fail("invalid-native-dv-sqref", part, "sqref", sqref)
    column_text, row_text = match.groups()
    if len(row_text) > 7:
        _fail("invalid-native-dv-sqref", part, "sqref", sqref)
    column = 0
    for character in column_text.upper():
        column = column * 26 + ord(character) - ord("A") + 1
    row = int(row_text)
    if column > _MAX_COLUMN or row > _MAX_ROW:
        _fail("invalid-native-dv-sqref", part, "sqref", sqref)
    return (row, column)


def _sqref(value: str | None, part: str) -> tuple[str, ...]:
    text = value or ""
    tokens = tuple(re.split(r"[ \t\r\n]+", text))
    if not text or any(not token for token in tokens):
        _fail("invalid-native-dv-sqref", part, "sqref", text)
    rectangles: list[tuple[int, int, int, int]] = []
    for token in tokens:
        endpoints = token.split(":")
        if len(endpoints) not in {1, 2}:
            _fail("invalid-native-dv-sqref", part, "sqref", text)
        first = _a1_endpoint(endpoints[0], part, text)
        last = _a1_endpoint(endpoints[-1], part, text)
        if first[0] > last[0] or first[1] > last[1]:
            _fail("invalid-native-dv-sqref", part, "sqref", text)
        rectangle = (first[0], first[1], last[0], last[1])
        if any(not (rectangle[2] < prior[0] or prior[2] < rectangle[0] or rectangle[3] < prior[1] or prior[3] < rectangle[1]) for prior in rectangles):
            _fail("overlapping-native-dv-sqref", part, "sqref", token)
        rectangles.append(rectangle)
    return tokens


def _native_owner_path(part: CanonicalPartURI, suffix: str) -> str:
    return f"{part.value}/worksheet/{suffix}"


def _validate_owned_tree(root: ET.Element, part: CanonicalPartURI) -> None:
    expected_parent = {_CONTAINER: _WORKSHEET, _RULE: _CONTAINER, _FORMULA1: _RULE, _FORMULA2: _RULE}
    local_owned = {"dataValidations": _CONTAINER, "dataValidation": _RULE, "formula1": _FORMULA1, "formula2": _FORMULA2}

    for element in root.iter():
        if element.tag == _X14_CONTAINER:
            _fail("unsupported_x14_content", part.value, "tag", _X14_CONTAINER)
        expected = expected_parent.get(element.tag)
        if expected is not None:
            # ElementTree has no parent API; validate legal placement below.
            continue
        local = element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""
        target = local_owned.get(local)
        if target is None or element.tag == target:
            continue
        # A foreign lookalike is dangerous only at a location where this
        # adapter owns that local name.  Else it remains foreign extension data.
        for parent in root.iter():
            if element in parent and parent.tag in {_WORKSHEET, _CONTAINER, _RULE}:
                _fail("owned-native-dv-namespace-collision", part.value, "tag", str(element.tag))

    def visit(parent: ET.Element) -> None:
        for child in parent:
            expected = expected_parent.get(child.tag)
            if expected is not None and parent.tag != expected:
                _fail("invalid-owned-native-dv-parent", part.value, "tag", str(child.tag))
            visit(child)

    visit(root)


def _formula(element: ET.Element, part: str, name: str) -> str:
    if element.attrib:
        _fail("unknown-native-dv-attribute", part, "attribute", sorted(element.attrib)[0])
    if len(element):
        _fail("invalid-native-dv-content", part, name, "nested")
    return element.text or ""


def _rule(element: ET.Element, part: CanonicalPartURI, index: int) -> NativeDataValidation:
    allowed = {"sqref", "type", "operator", "allowBlank", "showDropDown", "showInputMessage", "showErrorMessage", "errorStyle", "imeMode", "errorTitle", "error", "promptTitle", "prompt", f"{{{_XR}}}uid"}
    unknown = sorted(set(element.attrib) - allowed)
    if unknown:
        _fail("unknown-native-dv-attribute", part.value, "attribute", unknown[0])
    if "sqref" not in element.attrib:
        _fail("missing-native-dv-attribute", part.value, "attribute", "sqref")
    if "type" not in element.attrib:
        _fail("missing-native-dv-attribute", part.value, "attribute", "type")
    kind = element.attrib["type"]
    if kind not in _TYPES:
        _fail("invalid-native-dv-type", part.value, "type", kind)
    operator = element.attrib.get("operator")
    if operator is not None and operator not in _OPERATORS:
        _fail("invalid-native-dv-operator", part.value, "operator", operator)
    if "errorStyle" in element.attrib and element.attrib["errorStyle"] not in _ERROR_STYLES:
        _fail("invalid-native-dv-error-style", part.value, "errorStyle", element.attrib["errorStyle"])
    if "imeMode" in element.attrib and element.attrib["imeMode"] not in _IME_MODES:
        _fail("invalid-native-dv-ime-mode", part.value, "imeMode", element.attrib["imeMode"])
    uid = element.attrib.get(f"{{{_XR}}}uid")
    if uid is not None and _GUID.fullmatch(uid) is None:
        _fail("invalid-native-dv-uid", part.value, "uid", uid)
    sqref = _sqref(element.attrib.get("sqref"), part.value)
    allow_blank = _boolean(element.attrib["allowBlank"], part.value, "allowBlank") if "allowBlank" in element.attrib else None
    show_drop_down = _boolean(element.attrib["showDropDown"], part.value, "showDropDown") if "showDropDown" in element.attrib else None
    show_input_message = _boolean(element.attrib["showInputMessage"], part.value, "showInputMessage") if "showInputMessage" in element.attrib else None
    show_error_message = _boolean(element.attrib["showErrorMessage"], part.value, "showErrorMessage") if "showErrorMessage" in element.attrib else None
    _mixed(element, part.value, "dataValidation")
    formulas: dict[str, str] = {}
    expected_order = [_FORMULA1, _FORMULA2]
    seen_order: list[int] = []
    for child in element:
        if child.tag not in {_FORMULA1, _FORMULA2}:
            _fail("invalid-native-dv-child", part.value, "tag", str(child.tag))
        position = expected_order.index(child.tag)
        if child.tag in formulas:
            _fail("duplicate-native-dv-child", part.value, child.tag.rsplit("}", 1)[-1], "")
        seen_order.append(position)
        formulas[child.tag] = _formula(child, part.value, child.tag.rsplit("}", 1)[-1])
    if seen_order != sorted(seen_order):
        _fail("invalid-native-dv-child-order", part.value, "tag", "formula2")
    formula1 = formulas.get(_FORMULA1)
    formula2 = formulas.get(_FORMULA2)
    if kind == "none":
        valid = operator is None and formula1 is None and formula2 is None
    elif kind in {"list", "custom"}:
        valid = operator is None and formula1 is not None and formula2 is None
    elif kind in _COMPARISON_TYPES:
        effective_operator = operator or "between"
        valid = formula1 is not None and ((effective_operator in _RANGE_OPERATORS) == (formula2 is not None))
    else:
        valid = False
    if not valid:
        _fail("invalid-native-dv-formula-cardinality", part.value, "formula", kind)
    return NativeDataValidation(
        _native_owner_path(part, f"dataValidations/dataValidation[{index}]"), sqref, kind,
        operator, allow_blank, show_drop_down, show_input_message, show_error_message,
        element.attrib.get("errorStyle"), element.attrib.get("imeMode"), element.attrib.get("errorTitle"), element.attrib.get("error"),
        element.attrib.get("promptTitle"), element.attrib.get("prompt"), uid, formula1, formula2,
    )


def _container(root: ET.Element, part: CanonicalPartURI) -> NativeDataValidations | None:
    _mixed(root, part.value, "worksheet")
    containers = [child for child in root if child.tag == _CONTAINER]
    if len(containers) > 1:
        _fail("duplicate-native-dv-container", part.value, "dataValidations", "")
    if not containers:
        return None
    element = containers[0]
    allowed = {"count", "disablePrompts", "xWindow", "yWindow"}
    unknown = sorted(set(element.attrib) - allowed)
    if unknown:
        _fail("unknown-native-dv-attribute", part.value, "attribute", unknown[0])
    if "count" not in element.attrib:
        _fail("missing-native-dv-attribute", part.value, "attribute", "count")
    count = _uint32(element.attrib["count"], part.value, "count")
    disable_prompts = _boolean(element.attrib["disablePrompts"], part.value, "disablePrompts") if "disablePrompts" in element.attrib else None
    x_window = _uint32(element.attrib["xWindow"], part.value, "xWindow") if "xWindow" in element.attrib else None
    y_window = _uint32(element.attrib["yWindow"], part.value, "yWindow") if "yWindow" in element.attrib else None
    _mixed(element, part.value, "dataValidations")
    rules = []
    for index, child in enumerate(element, start=1):
        if child.tag != _RULE:
            _fail("invalid-native-dv-container-child", part.value, "tag", str(child.tag))
        rules.append(_rule(child, part, index))
    if count != len(rules):
        _fail("native-dv-count-mismatch", part.value, "count", element.attrib["count"])
    return NativeDataValidations(
        _native_owner_path(part, "dataValidations"), count,
        disable_prompts, x_window, y_window,
        tuple(rules),
    )


def read_worksheet_native_data_validation_semantics(package_path: os.PathLike[str] | str) -> WorkbookNativeDvSemantics:
    """Read only topology-owned native data validations; never mutate a package."""
    path = _coerce_package_path(package_path)
    topology = read_workbook_topology(path)
    records = []
    for worksheet in topology.worksheets:
        part = worksheet.worksheet_part
        root = _xml(_member(path, part), part)
        _validate_owned_tree(root, part)
        records.append(WorksheetNativeDvSemantics(worksheet, _container(root, part)))
    return WorkbookNativeDvSemantics(tuple(records))
