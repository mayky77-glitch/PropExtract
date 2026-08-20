"""Strict, immutable native SpreadsheetML conditional-formatting readers."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Final, Iterator
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile
import zlib

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology


_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_X14: Final = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
_XR: Final = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
_WORKSHEET: Final = f"{{{_SML}}}worksheet"
_CONTAINER: Final = f"{{{_SML}}}conditionalFormatting"
_RULE: Final = f"{{{_SML}}}cfRule"
_FORMULA: Final = f"{{{_SML}}}formula"
_UID: Final = f"{{{_XR}}}uid"
_X14_LOCALS: Final = frozenset({"conditionalFormattings", "conditionalFormatting", "cfRule"})
_OWNED_LOCALS: Final = frozenset({"conditionalFormatting", "cfRule"})
_XML_WHITESPACE: Final = frozenset({" ", "\t", "\r", "\n"})
_BOOLEANS: Final = {"0": False, "1": True, "false": False, "true": True}
_MAX_ROW: Final = 1_048_576
_MAX_COLUMN: Final = 16_384
_MAX_INT32: Final = 2_147_483_647
_MAX_UINT32: Final = 4_294_967_295
_SUPPORTED_RULE_TYPES: Final = frozenset({
    "expression",
    "uniqueValues",
    "duplicateValues",
    "containsBlanks",
    "notContainsBlanks",
    "containsErrors",
    "notContainsErrors",
})
_RULE_ATTRIBUTES: Final = frozenset({"type", "priority", "dxfId", "stopIfTrue"})

__all__ = (
    "NativeCfA1Range",
    "NativeCfContainerInventory",
    "NativeCfRuleCore",
    "NativeCfRuleCoreContainer",
    "OPCWorksheetNativeCfReaderError",
    "WorkbookNativeCfContainerInventory",
    "WorkbookNativeCfPresence",
    "WorkbookNativeCfRuleCoreSemantics",
    "WorksheetNativeCfContainerInventory",
    "WorksheetNativeCfPresence",
    "WorksheetNativeCfRuleCoreSemantics",
    "read_worksheet_native_cf_container_inventory",
    "read_worksheet_native_cf_presence",
    "read_worksheet_native_cf_rule_core_semantics",
)


@dataclass(frozen=True)
class NativeCfA1Range:
    start_coordinate: str
    end_coordinate: str
    min_row: int
    min_column: int
    max_row: int
    max_column: int


@dataclass(frozen=True)
class NativeCfContainerInventory:
    owner_path: str
    sqref: tuple[NativeCfA1Range, ...]
    pivot: bool | None
    uid: str | None
    rule_count: int


@dataclass(frozen=True)
class WorksheetNativeCfContainerInventory:
    worksheet: WorksheetDescriptor
    containers: tuple[NativeCfContainerInventory, ...]


@dataclass(frozen=True)
class WorkbookNativeCfContainerInventory:
    worksheets: tuple[WorksheetNativeCfContainerInventory, ...]


@dataclass(frozen=True)
class NativeCfRuleCore:
    owner_path: str
    document_order: int
    type: str
    priority: int
    dxf_id: int | None
    stop_if_true: bool | None
    formulas: tuple[str, ...]


@dataclass(frozen=True)
class NativeCfRuleCoreContainer:
    container: NativeCfContainerInventory
    rules: tuple[NativeCfRuleCore, ...]


@dataclass(frozen=True)
class WorksheetNativeCfRuleCoreSemantics:
    worksheet: WorksheetDescriptor
    containers: tuple[NativeCfRuleCoreContainer, ...]


@dataclass(frozen=True)
class WorkbookNativeCfRuleCoreSemantics:
    worksheets: tuple[WorksheetNativeCfRuleCoreSemantics, ...]


@dataclass(frozen=True)
class WorksheetNativeCfPresence:
    worksheet: WorksheetDescriptor
    has_native_conditional_formatting: bool


@dataclass(frozen=True)
class WorkbookNativeCfPresence:
    worksheets: tuple[WorksheetNativeCfPresence, ...]


@dataclass
class OPCWorksheetNativeCfReaderError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetNativeCfReaderError(code, subject, field, detail)


def _coerce_package_path(value: os.PathLike[str] | str) -> str:
    subject = f"{type(value).__module__}.{type(value).__qualname__}"
    try:
        path = os.fspath(value)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except Exception as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str):
        _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path:
        _fail("unreadable-package", path, "path", "embedded-nul")
    return path


def _member(path: str, part: CanonicalPartURI) -> bytes:
    """Read exactly one raw canonical ZIP member owned by topology."""
    try:
        with ZipFile(path) as archive:
            matches = []
            for info in archive.infolist():
                try:
                    canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError:
                    if _case_dot_key(info.filename) != part.value.casefold():
                        _fail("unreadable-worksheet-part", part.value, "member", "invalid-member-name")
                    matches.append(info)
                    continue
                if canonical == part or canonical.value.casefold() == part.value.casefold() or (
                    _case_dot_key(info.filename) == part.value.casefold()
                ):
                    matches.append(info)
            if not matches:
                _fail("missing-worksheet-member", part.value, "member", part.value)
            if len(matches) != 1:
                _fail("ambiguous-worksheet-member", part.value, "member", part.value)
            info = matches[0]
            if info.filename != part.value:
                _fail("noncanonical-worksheet-member", part.value, "member", info.filename)
            return archive.read(info)
    except OPCWorksheetNativeCfReaderError:
        raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError, zlib.error) as error:
        _fail("unreadable-worksheet-part", part.value, "xml", type(error).__name__)
    raise AssertionError("unreachable")


def _xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    """Use the sole worksheet XML boundary, retaining the original bytes."""
    try:
        root = ET.fromstring(payload)
    except LookupError:
        _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except ValueError:
        _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except ET.ParseError as error:
        if "unknown encoding" in str(error).lower():
            _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    except UnicodeError:
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    return root


def _worksheet_trees(package_path: os.PathLike[str] | str) -> Iterator[tuple[WorksheetDescriptor, CanonicalPartURI, ET.Element]]:
    """Shared package/topology/member/XML pipeline for both public readers."""
    path = _coerce_package_path(package_path)
    topology = read_workbook_topology(path)
    for worksheet in topology.worksheets:
        part = worksheet.worksheet_part
        yield worksheet, part, _xml(_member(path, part), part)


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _case_dot_key(value: str) -> str | None:
    """Normalize only raw case and dot aliases for member rejection."""
    if not value or value.startswith("/") or value.endswith("/") or "//" in value:
        return None
    segments: list[str] = []
    for segment in value.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if not segments:
                return None
            segments.pop()
            continue
        segments.append(segment)
    return "/".join(segments).casefold()


def _x14_hard_stop(root: ET.Element, part: CanonicalPartURI) -> None:
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith(f"{{{_X14}}}") and _local(element.tag) in _X14_LOCALS:
            _fail("unsupported_x14_content", part.value, "tag", element.tag)


def _validate_worksheet_root(root: ET.Element, part: CanonicalPartURI) -> None:
    if root.tag != _WORKSHEET:
        _fail("invalid-worksheet-root", part.value, "root", str(root.tag))


def _nonwhite(value: str | None) -> bool:
    return bool(value and not value.isspace())


def _owned_mixed(element: ET.Element, part: CanonicalPartURI) -> None:
    name = _local(element.tag)
    if _nonwhite(element.text):
        _fail("invalid-native-cf-content", part.value, name, "text")
    for child in element:
        if _nonwhite(child.tail):
            _fail("invalid-native-cf-content", part.value, name, "tail")


def _validate_owned_placement(root: ET.Element, part: CanonicalPartURI) -> None:
    """Validate placement and namespace only for tags this reader owns."""
    direct_containers = frozenset(child for child in root if child.tag == _CONTAINER)
    for parent in root.iter():
        for child in parent:
            local = _local(child.tag)
            if child.tag in {_CONTAINER, _RULE}:
                valid = (child.tag == _CONTAINER and parent is root) or (
                    child.tag == _RULE and parent in direct_containers
                )
                if not valid:
                    _fail("invalid-owned-native-cf-parent", part.value, "tag", str(child.tag))
                continue
            if local in _OWNED_LOCALS and (parent is root or parent in direct_containers):
                _fail("owned-native-cf-namespace-collision", part.value, "tag", str(child.tag))


def _validate_presence_content(root: ET.Element, part: CanonicalPartURI) -> None:
    for container in root:
        if container.tag != _CONTAINER:
            continue
        _owned_mixed(container, part)
        for rule in container:
            if rule.tag == _RULE:
                _owned_mixed(rule, part)


def _presence(root: ET.Element) -> bool:
    return any(child.tag == _CONTAINER for child in root)


def _boolean(value: str, part: CanonicalPartURI, field: str) -> bool:
    result = _BOOLEANS.get(value)
    if result is None and value not in _BOOLEANS:
        _fail("invalid-native-cf-boolean", part.value, field, value)
    return result


def _collapse_xml_whitespace(value: str) -> str:
    """Normalize only the four XML whitespace characters."""
    words = _sqref_tokens(value)
    return " ".join(words)


def _ascii_digits(value: str) -> bool:
    return bool(value) and all("0" <= character <= "9" for character in value)


def _bounded_decimal(value: str, maximum: int) -> int | None:
    """Return an unsigned decimal without converting unbounded lexical input."""
    significant = value.lstrip("0") or "0"
    maximum_text = str(maximum)
    if len(significant) > len(maximum_text) or (
        len(significant) == len(maximum_text) and significant > maximum_text
    ):
        return None
    return int(significant)


def _signed_int32(value: str, part: CanonicalPartURI, field: str) -> int:
    lexical = _collapse_xml_whitespace(value)
    sign = -1 if lexical.startswith("-") else 1
    digits = lexical[1:] if lexical.startswith(("+", "-")) else lexical
    if not _ascii_digits(digits):
        _fail("invalid-native-cf-priority", part.value, field, value)
    result = _bounded_decimal(digits, _MAX_INT32)
    if result is None or sign * result < 1:
        _fail("invalid-native-cf-priority", part.value, field, value)
    return result


def _uint32(value: str, part: CanonicalPartURI, field: str) -> int:
    lexical = _collapse_xml_whitespace(value)
    negative = lexical.startswith("-")
    digits = lexical[1:] if lexical.startswith(("+", "-")) else lexical
    valid = _ascii_digits(digits) and (not negative or set(digits) == {"0"})
    if not valid:
        _fail("invalid-native-cf-dxf-id", part.value, field, value)
    result = _bounded_decimal(digits, _MAX_UINT32)
    if result is None:
        _fail("invalid-native-cf-dxf-id", part.value, field, value)
    return result


def _a1_endpoint(value: str, part: CanonicalPartURI, sqref: str) -> tuple[str, int, int]:
    position = 0
    if position < len(value) and value[position] == "$":
        position += 1
    column_start = position
    while position < len(value) and value[position].isalpha() and value[position].isascii():
        position += 1
    column_text = value[column_start:position]
    if not 1 <= len(column_text) <= 3:
        _fail("invalid-native-cf-sqref", part.value, "sqref", sqref)
    if position < len(value) and value[position] == "$":
        position += 1
    row_text = value[position:]
    if not 1 <= len(row_text) <= 7 or not row_text.isascii() or not row_text.isdecimal() or row_text[0] == "0":
        _fail("invalid-native-cf-sqref", part.value, "sqref", sqref)
    column = 0
    for character in column_text.upper():
        column = column * 26 + ord(character) - ord("A") + 1
    row = int(row_text)
    if column > _MAX_COLUMN or row > _MAX_ROW:
        _fail("invalid-native-cf-sqref", part.value, "sqref", sqref)
    return f"{column_text.upper()}{row}", row, column


def _sqref_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    token: list[str] = []
    for character in value:
        if character in _XML_WHITESPACE:
            if token:
                tokens.append("".join(token))
                token.clear()
        else:
            token.append(character)
    if token:
        tokens.append("".join(token))
    return tuple(tokens)


def _sqref(value: str | None, part: CanonicalPartURI) -> tuple[NativeCfA1Range, ...]:
    text = "" if value is None else value
    tokens = _sqref_tokens(text)
    if not tokens:
        _fail("invalid-native-cf-sqref", part.value, "sqref", text)
    rectangles: list[NativeCfA1Range] = []
    lexical_tokens: set[str] = set()
    normalized_rectangles: set[tuple[int, int, int, int]] = set()
    for token in tokens:
        endpoints = token.split(":")
        if len(endpoints) not in {1, 2}:
            _fail("invalid-native-cf-sqref", part.value, "sqref", text)
        start, min_row, min_column = _a1_endpoint(endpoints[0], part, text)
        end, max_row, max_column = _a1_endpoint(endpoints[-1], part, text)
        if min_row > max_row or min_column > max_column:
            _fail("invalid-native-cf-sqref", part.value, "sqref", text)
        rectangle = NativeCfA1Range(start, end, min_row, min_column, max_row, max_column)
        normalized = (min_row, min_column, max_row, max_column)
        if token in lexical_tokens or normalized in normalized_rectangles:
            _fail("duplicate-native-cf-sqref", part.value, "sqref", token)
        lexical_tokens.add(token)
        normalized_rectangles.add(normalized)
        if any(not (
            rectangle.max_row < prior.min_row or prior.max_row < rectangle.min_row
            or rectangle.max_column < prior.min_column or prior.max_column < rectangle.min_column
        ) for prior in rectangles):
            _fail("overlapping-native-cf-sqref", part.value, "sqref", token)
        rectangles.append(rectangle)
    return tuple(rectangles)


def _braced_guid(value: str) -> bool:
    return (
        len(value) == 38
        and value[0] == "{"
        and value[-1] == "}"
        and all(value[index] == "-" for index in (9, 14, 19, 24))
        and all(character in "0123456789abcdefABCDEF" for index, character in enumerate(value)
                if index not in {0, 9, 14, 19, 24, 37})
    )


def _native_owner_path(part: CanonicalPartURI, index: int) -> str:
    return f"{part.value}/worksheet/conditionalFormatting[{index}]"


def _container_inventory(element: ET.Element, part: CanonicalPartURI, index: int) -> NativeCfContainerInventory:
    allowed = {"sqref", "pivot", _UID}
    unknown = sorted(set(element.attrib) - allowed)
    if unknown:
        _fail("unknown-native-cf-attribute", part.value, "attribute", unknown[0])
    if "sqref" not in element.attrib:
        _fail("missing-native-cf-attribute", part.value, "attribute", "sqref")
    uid = element.attrib.get(_UID)
    if uid is not None and not _braced_guid(uid):
        _fail("invalid-native-cf-uid", part.value, "uid", uid)
    pivot = _boolean(element.attrib["pivot"], part, "pivot") if "pivot" in element.attrib else None
    rules = 0
    for child in element:
        if child.tag != _RULE:
            _fail("invalid-native-cf-container-child", part.value, "tag", str(child.tag))
        rules += 1
    return NativeCfContainerInventory(
        _native_owner_path(part, index), _sqref(element.attrib["sqref"], part), pivot, uid, rules,
    )


def _rule_owner_path(container: NativeCfContainerInventory, index: int) -> str:
    return f"{container.owner_path}/cfRule[{index}]"


def _rule_attributes(element: ET.Element, part: CanonicalPartURI) -> tuple[str, int, int | None, bool | None]:
    unknown = sorted(set(element.attrib) - _RULE_ATTRIBUTES)
    if unknown:
        _fail("unknown-native-cf-rule-attribute", part.value, "attribute", unknown[0])
    for name in ("type", "priority"):
        if name not in element.attrib:
            _fail("missing-native-cf-rule-attribute", part.value, "attribute", name)
    rule_type = element.attrib["type"]
    if rule_type not in _SUPPORTED_RULE_TYPES:
        _fail("unsupported-native-cf-rule-type", part.value, "type", rule_type)
    priority = _signed_int32(element.attrib["priority"], part, "priority")
    dxf_id = _uint32(element.attrib["dxfId"], part, "dxfId") if "dxfId" in element.attrib else None
    stop_if_true = _boolean(element.attrib["stopIfTrue"], part, "stopIfTrue") if "stopIfTrue" in element.attrib else None
    return rule_type, priority, dxf_id, stop_if_true


def _formula(element: ET.Element, part: CanonicalPartURI) -> str:
    if element.attrib:
        _fail("invalid-native-cf-formula-attribute", part.value, "attribute", sorted(element.attrib)[0])
    if list(element):
        _fail("invalid-native-cf-formula-content", part.value, "formula", "nested")
    text = element.text
    if text is None or not _collapse_xml_whitespace(text):
        _fail("invalid-native-cf-formula-content", part.value, "formula", "blank")
    return text


def _rule_core(
    element: ET.Element,
    part: CanonicalPartURI,
    container: NativeCfContainerInventory,
    rule_index: int,
    document_order: int,
    priorities: set[int],
) -> NativeCfRuleCore:
    rule_type, priority, dxf_id, stop_if_true = _rule_attributes(element, part)
    if priority in priorities:
        _fail("duplicate-native-cf-priority", part.value, "priority", element.attrib["priority"])
    formulas: list[str] = []
    for child in element:
        if child.tag != _FORMULA:
            _fail("invalid-native-cf-rule-child", part.value, "tag", str(child.tag))
        formulas.append(_formula(child, part))
    expected = 1 if rule_type == "expression" else 0
    if len(formulas) != expected:
        _fail("invalid-native-cf-formula-cardinality", part.value, "type", rule_type)
    priorities.add(priority)
    return NativeCfRuleCore(
        _rule_owner_path(container, rule_index),
        document_order,
        rule_type,
        priority,
        dxf_id,
        stop_if_true,
        tuple(formulas),
    )


def read_worksheet_native_cf_presence(package_path: os.PathLike[str] | str) -> WorkbookNativeCfPresence:
    """Inventory native CF container presence; never parse semantic CF content."""
    records = []
    for worksheet, part, root in _worksheet_trees(package_path):
        _x14_hard_stop(root, part)
        _validate_worksheet_root(root, part)
        _validate_owned_placement(root, part)
        _validate_presence_content(root, part)
        records.append(WorksheetNativeCfPresence(worksheet, _presence(root)))
    return WorkbookNativeCfPresence(tuple(records))


def read_worksheet_native_cf_container_inventory(
    package_path: os.PathLike[str] | str,
) -> WorkbookNativeCfContainerInventory:
    """Inventory direct native CF containers without interpreting their rules."""
    records = []
    for worksheet, part, root in _worksheet_trees(package_path):
        _x14_hard_stop(root, part)
        _validate_worksheet_root(root, part)
        _validate_owned_placement(root, part)
        _validate_presence_content(root, part)
        containers = tuple(
            _container_inventory(element, part, index)
            for index, element in enumerate((child for child in root if child.tag == _CONTAINER), start=1)
        )
        records.append(WorksheetNativeCfContainerInventory(worksheet, containers))
    return WorkbookNativeCfContainerInventory(tuple(records))


def read_worksheet_native_cf_rule_core_semantics(
    package_path: os.PathLike[str] | str,
) -> WorkbookNativeCfRuleCoreSemantics:
    """Read the frozen native-CF rule core after the accepted container boundary."""
    records = []
    for worksheet, part, root in _worksheet_trees(package_path):
        _x14_hard_stop(root, part)
        _validate_worksheet_root(root, part)
        _validate_owned_placement(root, part)
        _validate_presence_content(root, part)
        priorities: set[int] = set()
        document_order = 0
        containers = []
        for container_index, element in enumerate((child for child in root if child.tag == _CONTAINER), start=1):
            container = _container_inventory(element, part, container_index)
            rules = []
            for rule_index, rule in enumerate(element, start=1):
                document_order += 1
                rules.append(_rule_core(rule, part, container, rule_index, document_order, priorities))
            containers.append(NativeCfRuleCoreContainer(container, tuple(rules)))
        records.append(WorksheetNativeCfRuleCoreSemantics(worksheet, tuple(containers)))
    return WorkbookNativeCfRuleCoreSemantics(tuple(records))
