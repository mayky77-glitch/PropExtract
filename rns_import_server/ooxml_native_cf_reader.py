"""Strict, lossless reader for native SpreadsheetML conditional formatting.

This reader intentionally owns only the native ``conditionalFormatting``
vocabulary.  It does not try to interpret x14 extensions: an extension child
inside a native conditional-formatting object is therefore rejected instead of
being silently dropped.  That makes it safe for a later writer to rely on the
typed output as a complete description of the native object it owns.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TypeAlias
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
MAX_ROW = 1_048_576
MAX_COLUMN = 16_384  # XFD

_GUID = re.compile(
    r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
)
_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)$")
_CELL_RANGE = re.compile(
    r"^(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*)(?::(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*))?$"
)


class NativeCfParseError(ValueError):
    """A stable, typed error for malformed or unsupported native CF XML."""

    def __init__(self, code: str, owner_path: str, detail: str = "") -> None:
        self.code = code
        self.owner_path = owner_path
        self.detail = detail
        suffix = f": {detail}" if detail else ""
        super().__init__(f"{code} at {owner_path}{suffix}")


@dataclass(frozen=True, slots=True)
class NativeCfFinding:
    code: str
    owner_path: str
    detail: str


@dataclass(frozen=True, slots=True)
class NativeCfvo:
    owner_path: str
    type: str
    value: str | None
    greater_than_or_equal: bool | None


@dataclass(frozen=True, slots=True)
class NativeColor:
    owner_path: str
    rgb: str | None
    indexed: int | None
    theme: int | None
    auto: bool | None
    tint: float | None


@dataclass(frozen=True, slots=True)
class NativeColorScale:
    owner_path: str
    thresholds: tuple[NativeCfvo, ...]
    colors: tuple[NativeColor, ...]


@dataclass(frozen=True, slots=True)
class NativeDataBar:
    owner_path: str
    thresholds: tuple[NativeCfvo, ...]
    color: NativeColor
    min_length: int | None
    max_length: int | None
    show_value: bool | None
    gradient: bool | None
    border: bool | None
    negative_bar_color_same_as_positive: bool | None
    negative_bar_border_color_same_as_positive: bool | None
    axis_position: str | None
    direction: str | None


@dataclass(frozen=True, slots=True)
class NativeIconSet:
    owner_path: str
    thresholds: tuple[NativeCfvo, ...]
    icon_set: str | None
    show_value: bool | None
    percent: bool | None
    reverse: bool | None


NativeCfPayload: TypeAlias = NativeColorScale | NativeDataBar | NativeIconSet | None


@dataclass(frozen=True, slots=True)
class NativeCfRule:
    owner_path: str
    type: str
    priority: int
    dxf_id: int | None
    stop_if_true: bool | None
    above_average: bool | None
    percent: bool | None
    bottom: bool | None
    operator: str | None
    text: str | None
    time_period: str | None
    rank: int | None
    standard_deviation: int | None
    equal_average: bool | None
    formulas: tuple[str, ...]
    payload: NativeCfPayload


@dataclass(frozen=True, slots=True)
class NativeConditionalFormatting:
    owner_path: str
    sqref: tuple[str, ...]
    pivot: bool | None
    uid: str | None
    rules: tuple[NativeCfRule, ...]


@dataclass(frozen=True, slots=True)
class NativeCfReadResult:
    worksheet_part: str
    containers: tuple[NativeConditionalFormatting, ...]
    findings: tuple[NativeCfFinding, ...] = ()

    @property
    def conditional_formattings(self) -> tuple[NativeConditionalFormatting, ...]:
        """Explicit alias for callers that prefer the XML vocabulary name."""
        return self.containers


_RULE_TYPES = frozenset({
    "expression", "cellIs", "colorScale", "dataBar", "iconSet", "top10",
    "uniqueValues", "duplicateValues", "containsText", "notContainsText",
    "beginsWith", "endsWith", "containsBlanks", "notContainsBlanks",
    "containsErrors", "notContainsErrors", "timePeriod", "aboveAverage",
})
_RULE_ATTRS = frozenset({
    "type", "dxfId", "priority", "stopIfTrue", "aboveAverage", "percent",
    "bottom", "operator", "text", "timePeriod", "rank", "stdDev", "equalAverage",
})
_OPERATORS = frozenset({
    "between", "notBetween", "equal", "notEqual", "greaterThan", "lessThan",
    "greaterThanOrEqual", "lessThanOrEqual",
})
_TIME_PERIODS = frozenset({
    "today", "yesterday", "tomorrow", "last7Days", "lastMonth", "nextMonth",
    "thisWeek", "lastWeek", "nextWeek", "thisMonth",
})
_CFVO_TYPES = frozenset({"min", "max", "num", "percent", "percentile", "formula", "autoMin", "autoMax"})
_AXIS_POSITIONS = frozenset({"automatic", "middle", "none"})
_DIRECTIONS = frozenset({"context", "leftToRight", "rightToLeft"})
_ICON_SETS = frozenset({
    "3Arrows", "3ArrowsGray", "3Flags", "3TrafficLights1", "3TrafficLights2",
    "3Signs", "3Symbols", "3Symbols2", "3Stars", "3Triangles", "4Arrows",
    "4ArrowsGray", "4RedToBlack", "4Rating", "4TrafficLights", "5Arrows",
    "5ArrowsGray", "5Quarters", "5Rating", "5Boxes",
})


def _qname(local: str) -> str:
    return f"{{{MAIN_NS}}}{local}"


def _is_main(element: ET.Element, local: str) -> bool:
    return element.tag == _qname(local)


def _path(worksheet_part: str, suffix: str) -> str:
    return f"{worksheet_part}#worksheet/{suffix}"


def _fail(code: str, owner_path: str, detail: str = "") -> None:
    raise NativeCfParseError(code, owner_path, detail)


def _strict_attrs(element: ET.Element, allowed: frozenset[str], owner_path: str) -> None:
    for name in element.attrib:
        if name not in allowed:
            _fail("unknown_attribute", owner_path, name)


def _required(attrs: dict[str, str], name: str, owner_path: str) -> str:
    value = attrs.get(name)
    if value is None or not value.strip():
        _fail("missing_required_attribute", owner_path, name)
    return value


def _bool(value: str | None, owner_path: str, name: str) -> bool | None:
    if value is None:
        return None
    if value in ("1", "true"):
        return True
    if value in ("0", "false"):
        return False
    _fail("invalid_boolean", owner_path, name)


def _integer(
    value: str | None, owner_path: str, name: str, *, minimum: int = 0, maximum: int | None = None,
) -> int | None:
    if value is None:
        return None
    if not re.fullmatch(r"[0-9]+", value):
        _fail("invalid_integer", owner_path, name)
    parsed = int(value)
    if parsed < minimum or (maximum is not None and parsed > maximum):
        _fail("integer_out_of_range", owner_path, name)
    return parsed


def _float(value: str | None, owner_path: str, name: str) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        _fail("invalid_float", owner_path, name)
    if not parsed == parsed or parsed in (float("inf"), float("-inf")):
        _fail("invalid_float", owner_path, name)
    return parsed


def _column_number(column: str) -> int:
    result = 0
    for char in column.upper():
        result = result * 26 + ord(char) - ord("A") + 1
    return result


def _validate_cell(value: str, owner_path: str) -> None:
    match = _CELL.fullmatch(value)
    if match is None:
        _fail("malformed_sqref", owner_path, value)
    if _column_number(match.group(1)) > MAX_COLUMN or int(match.group(2)) > MAX_ROW:
        _fail("sqref_out_of_bounds", owner_path, value)


def _sqref(value: str | None, owner_path: str) -> tuple[str, ...]:
    if value is None or not value.strip():
        _fail("missing_sqref", owner_path)
    tokens = tuple(value.split())
    if not tokens:
        _fail("empty_sqref", owner_path)
    for token in tokens:
        match = _CELL_RANGE.fullmatch(token)
        if match is None:
            _fail("malformed_sqref", owner_path, token)
        _validate_cell(match.group(1), owner_path)
        if match.group(2) is not None:
            _validate_cell(match.group(2), owner_path)
    return tokens


def _uid(value: str | None, owner_path: str) -> str | None:
    if value is None:
        return None
    if not _GUID.fullmatch(value):
        _fail("invalid_uid", owner_path, value)
    return value


def _enum(value: str | None, accepted: frozenset[str], owner_path: str, name: str) -> str | None:
    if value is not None and value not in accepted:
        _fail("invalid_enum", owner_path, name)
    return value


def _parse_cfvo(element: ET.Element, owner_path: str) -> NativeCfvo:
    _strict_attrs(element, frozenset({"type", "val", "gte"}), owner_path)
    value_type = _required(element.attrib, "type", owner_path)
    _enum(value_type, _CFVO_TYPES, owner_path, "type")
    value = element.attrib.get("val")
    if value_type in {"num", "percent", "percentile", "formula"} and (value is None or not value.strip()):
        _fail("missing_required_attribute", owner_path, "val")
    if list(element):
        _fail("unknown_owned_content", owner_path, "cfvo child")
    return NativeCfvo(owner_path, value_type, value, _bool(element.attrib.get("gte"), owner_path, "gte"))


def _parse_color(element: ET.Element, owner_path: str) -> NativeColor:
    _strict_attrs(element, frozenset({"rgb", "indexed", "theme", "auto", "tint"}), owner_path)
    if list(element):
        _fail("unknown_owned_content", owner_path, "color child")
    rgb = element.attrib.get("rgb")
    if rgb is not None and not re.fullmatch(r"[0-9A-Fa-f]{8}", rgb):
        _fail("invalid_color", owner_path, "rgb")
    indexed = _integer(element.attrib.get("indexed"), owner_path, "indexed")
    theme = _integer(element.attrib.get("theme"), owner_path, "theme")
    auto = _bool(element.attrib.get("auto"), owner_path, "auto")
    tint = _float(element.attrib.get("tint"), owner_path, "tint")
    if tint is not None and not -1 <= tint <= 1:
        _fail("float_out_of_range", owner_path, "tint")
    if sum(item is not None for item in (rgb, indexed, theme, auto)) != 1:
        _fail("invalid_color", owner_path, "one color source required")
    return NativeColor(owner_path, rgb, indexed, theme, auto, tint)


def _parse_color_scale(element: ET.Element, owner_path: str) -> NativeColorScale:
    _strict_attrs(element, frozenset(), owner_path)
    children = list(element)
    threshold_elements = [child for child in children if _is_main(child, "cfvo")]
    color_elements = [child for child in children if _is_main(child, "color")]
    if len(children) != len(threshold_elements) + len(color_elements):
        _fail("unknown_owned_content", owner_path, "colorScale child")
    split = len(threshold_elements)
    if children[:split] != threshold_elements or children[split:] != color_elements:
        _fail("invalid_child_order", owner_path, "colorScale")
    if not 2 <= len(threshold_elements) <= 3 or len(threshold_elements) != len(color_elements):
        _fail("invalid_payload_cardinality", owner_path, "colorScale")
    return NativeColorScale(
        owner_path,
        tuple(_parse_cfvo(child, f"{owner_path}/cfvo[{index}]") for index, child in enumerate(threshold_elements, 1)),
        tuple(_parse_color(child, f"{owner_path}/color[{index}]") for index, child in enumerate(color_elements, 1)),
    )


def _parse_data_bar(element: ET.Element, owner_path: str) -> NativeDataBar:
    allowed = frozenset({
        "minLength", "maxLength", "showValue", "gradient", "border",
        "negativeBarColorSameAsPositive", "negativeBarBorderColorSameAsPositive",
        "axisPosition", "direction",
    })
    _strict_attrs(element, allowed, owner_path)
    children = list(element)
    threshold_elements = [child for child in children if _is_main(child, "cfvo")]
    color_elements = [child for child in children if _is_main(child, "color")]
    if len(children) != len(threshold_elements) + len(color_elements):
        _fail("unknown_owned_content", owner_path, "dataBar child")
    if children[:len(threshold_elements)] != threshold_elements or children[len(threshold_elements):] != color_elements:
        _fail("invalid_child_order", owner_path, "dataBar")
    if len(threshold_elements) != 2 or len(color_elements) != 1:
        _fail("invalid_payload_cardinality", owner_path, "dataBar")
    return NativeDataBar(
        owner_path,
        tuple(_parse_cfvo(child, f"{owner_path}/cfvo[{index}]") for index, child in enumerate(threshold_elements, 1)),
        _parse_color(color_elements[0], f"{owner_path}/color[1]"),
        _integer(element.attrib.get("minLength"), owner_path, "minLength", maximum=100),
        _integer(element.attrib.get("maxLength"), owner_path, "maxLength", maximum=100),
        _bool(element.attrib.get("showValue"), owner_path, "showValue"),
        _bool(element.attrib.get("gradient"), owner_path, "gradient"),
        _bool(element.attrib.get("border"), owner_path, "border"),
        _bool(element.attrib.get("negativeBarColorSameAsPositive"), owner_path, "negativeBarColorSameAsPositive"),
        _bool(element.attrib.get("negativeBarBorderColorSameAsPositive"), owner_path, "negativeBarBorderColorSameAsPositive"),
        _enum(element.attrib.get("axisPosition"), _AXIS_POSITIONS, owner_path, "axisPosition"),
        _enum(element.attrib.get("direction"), _DIRECTIONS, owner_path, "direction"),
    )


def _parse_icon_set(element: ET.Element, owner_path: str) -> NativeIconSet:
    _strict_attrs(element, frozenset({"iconSet", "showValue", "percent", "reverse"}), owner_path)
    children = list(element)
    if not all(_is_main(child, "cfvo") for child in children):
        _fail("unknown_owned_content", owner_path, "iconSet child")
    icon_set = _enum(element.attrib.get("iconSet"), _ICON_SETS, owner_path, "iconSet")
    expected_thresholds = int((icon_set or "3TrafficLights1")[0])
    if len(children) != expected_thresholds:
        _fail("invalid_payload_cardinality", owner_path, "iconSet")
    return NativeIconSet(
        owner_path,
        tuple(_parse_cfvo(child, f"{owner_path}/cfvo[{index}]") for index, child in enumerate(children, 1)),
        icon_set,
        _bool(element.attrib.get("showValue"), owner_path, "showValue"),
        _bool(element.attrib.get("percent"), owner_path, "percent"),
        _bool(element.attrib.get("reverse"), owner_path, "reverse"),
    )


def _parse_rule(element: ET.Element, owner_path: str) -> NativeCfRule:
    _strict_attrs(element, _RULE_ATTRS, owner_path)
    rule_type = _required(element.attrib, "type", owner_path)
    _enum(rule_type, _RULE_TYPES, owner_path, "type")
    priority = _integer(_required(element.attrib, "priority", owner_path), owner_path, "priority", minimum=1)
    assert priority is not None
    dxf_id = _integer(element.attrib.get("dxfId"), owner_path, "dxfId")
    operator = _enum(element.attrib.get("operator"), _OPERATORS, owner_path, "operator")
    time_period = _enum(element.attrib.get("timePeriod"), _TIME_PERIODS, owner_path, "timePeriod")
    rank = _integer(element.attrib.get("rank"), owner_path, "rank", minimum=1, maximum=100)
    standard_deviation = _integer(element.attrib.get("stdDev"), owner_path, "stdDev", minimum=0)
    children = list(element)
    formula_elements = [child for child in children if _is_main(child, "formula")]
    payload_elements = [child for child in children if _is_main(child, "colorScale") or _is_main(child, "dataBar") or _is_main(child, "iconSet")]
    if len(children) != len(formula_elements) + len(payload_elements):
        _fail("unknown_owned_content", owner_path, "cfRule child")
    if len(payload_elements) > 1:
        _fail("invalid_payload_cardinality", owner_path, "cfRule")
    if formula_elements and children[:len(formula_elements)] != formula_elements:
        _fail("invalid_child_order", owner_path, "formula")
    if payload_elements and children[len(formula_elements):] != payload_elements:
        _fail("invalid_child_order", owner_path, "payload")
    if payload_elements and formula_elements:
        _fail("invalid_child_order", owner_path, "formula and payload")
    formulas: list[str] = []
    for index, formula in enumerate(formula_elements, 1):
        formula_path = f"{owner_path}/formula[{index}]"
        _strict_attrs(formula, frozenset(), formula_path)
        if list(formula) or formula.text is None or not formula.text.strip():
            _fail("invalid_formula", formula_path)
        formulas.append(formula.text)
    payload: NativeCfPayload = None
    if payload_elements:
        payload_element = payload_elements[0]
        if _is_main(payload_element, "colorScale"):
            payload = _parse_color_scale(payload_element, f"{owner_path}/colorScale[1]")
        elif _is_main(payload_element, "dataBar"):
            payload = _parse_data_bar(payload_element, f"{owner_path}/dataBar[1]")
        else:
            payload = _parse_icon_set(payload_element, f"{owner_path}/iconSet[1]")
    expected_payload = {"colorScale": NativeColorScale, "dataBar": NativeDataBar, "iconSet": NativeIconSet}.get(rule_type)
    if expected_payload is not None and not isinstance(payload, expected_payload):
        _fail("missing_required_payload", owner_path, rule_type)
    if expected_payload is None and payload is not None:
        _fail("unexpected_payload", owner_path, rule_type)
    if rule_type in {"expression", "cellIs"} and not formulas:
        _fail("missing_required_formula", owner_path, rule_type)
    return NativeCfRule(
        owner_path=owner_path,
        type=rule_type,
        priority=priority,
        dxf_id=dxf_id,
        stop_if_true=_bool(element.attrib.get("stopIfTrue"), owner_path, "stopIfTrue"),
        above_average=_bool(element.attrib.get("aboveAverage"), owner_path, "aboveAverage"),
        percent=_bool(element.attrib.get("percent"), owner_path, "percent"),
        bottom=_bool(element.attrib.get("bottom"), owner_path, "bottom"),
        operator=operator,
        text=element.attrib.get("text"),
        time_period=time_period,
        rank=rank,
        standard_deviation=standard_deviation,
        equal_average=_bool(element.attrib.get("equalAverage"), owner_path, "equalAverage"),
        formulas=tuple(formulas),
        payload=payload,
    )


def read_native_conditional_formatting(worksheet_part: str, worksheet_xml: str | bytes) -> NativeCfReadResult:
    """Read every native conditional-formatting container in worksheet order.

    The input is only the worksheet XML part, not a whole XLSX.  Results are
    immutable and no recovery/defaulting is performed for malformed source.
    """
    if not isinstance(worksheet_part, str) or not worksheet_part or worksheet_part.strip() != worksheet_part:
        _fail("invalid_worksheet_part", str(worksheet_part), "worksheet_part")
    root_path = _path(worksheet_part, "")
    if not isinstance(worksheet_xml, (str, bytes)):
        _fail("invalid_worksheet_xml", root_path)
    try:
        root = ET.fromstring(worksheet_xml)
    except ET.ParseError as exc:
        _fail("invalid_xml", root_path, str(exc))
    if not _is_main(root, "worksheet"):
        _fail("invalid_worksheet_root", root_path)
    containers: list[NativeConditionalFormatting] = []
    priorities: set[int] = set()
    for group_index, element in enumerate((child for child in root if _is_main(child, "conditionalFormatting")), 1):
        owner_path = _path(worksheet_part, f"conditionalFormatting[{group_index}]")
        _strict_attrs(element, frozenset({"sqref", "pivot", f"{{{XR_NS}}}uid"}), owner_path)
        rules: list[NativeCfRule] = []
        for rule_index, child in enumerate(element, 1):
            rule_path = f"{owner_path}/cfRule[{rule_index}]"
            if not _is_main(child, "cfRule"):
                _fail("unknown_owned_content", owner_path, str(child.tag))
            rule = _parse_rule(child, rule_path)
            if rule.priority in priorities:
                _fail("duplicate_priority", rule_path, str(rule.priority))
            priorities.add(rule.priority)
            rules.append(rule)
        containers.append(NativeConditionalFormatting(
            owner_path=owner_path,
            sqref=_sqref(element.attrib.get("sqref"), owner_path),
            pivot=_bool(element.attrib.get("pivot"), owner_path, "pivot"),
            uid=_uid(element.attrib.get(f"{{{XR_NS}}}uid"), owner_path),
            rules=tuple(rules),
        ))
    return NativeCfReadResult(worksheet_part=worksheet_part, containers=tuple(containers))


# Short aliases keep callers from having to duplicate the native vocabulary.
parse_native_conditional_formatting = read_native_conditional_formatting
read_native_cf = read_native_conditional_formatting


__all__ = [
    "MAIN_NS", "XR_NS", "MAX_ROW", "NativeCfParseError", "NativeCfFinding", "NativeCfvo",
    "NativeColor", "NativeColorScale", "NativeDataBar", "NativeIconSet", "NativeCfRule",
    "NativeConditionalFormatting", "NativeCfReadResult", "read_native_conditional_formatting",
    "parse_native_conditional_formatting", "read_native_cf",
]
