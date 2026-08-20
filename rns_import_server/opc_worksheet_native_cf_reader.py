"""Strict, immutable native SpreadsheetML conditional-formatting presence."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Final
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
_EXT_LIST: Final = f"{{{_SML}}}extLst"
_X14_LOCALS: Final = frozenset({"conditionalFormattings", "conditionalFormatting", "cfRule"})
_OWNED_LOCALS: Final = frozenset({"conditionalFormatting", "cfRule"})
_XML_WHITESPACE: Final = " \t\r\n"
_CELL: Final = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})\Z")
_GUID: Final = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}\Z")
_BOOLEANS: Final = {"0": False, "1": True, "false": False, "true": True}
_MAX_ROW: Final = 1_048_576
_MAX_COLUMN: Final = 16_384
_XML_NAME: Final = re.compile(r"[A-Za-z_:][A-Za-z0-9_.:-]*")
_XML_DECLARATION_ENCODING: Final = re.compile(
    br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

__all__ = (
    "OPCWorksheetNativeCfReaderError",
    "NativeCfA1Range",
    "NativeCfContainerInventory",
    "WorksheetNativeCfContainerInventory",
    "WorkbookNativeCfContainerInventory",
    "WorkbookNativeCfPresence",
    "WorksheetNativeCfPresence",
    "read_worksheet_native_cf_container_inventory",
    "read_worksheet_native_cf_presence",
)


@dataclass(frozen=True)
class WorksheetNativeCfPresence:
    worksheet: WorksheetDescriptor
    has_native_conditional_formatting: bool


@dataclass(frozen=True)
class WorkbookNativeCfPresence:
    worksheets: tuple[WorksheetNativeCfPresence, ...]


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
    try:
        root = ET.fromstring(payload)
    except LookupError:
        _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except ValueError:
        if _declares_xml_encoding(payload):
            _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    except ET.ParseError as error:
        if "unknown encoding" in str(error).lower():
            _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    except UnicodeError:
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    if root.tag != _WORKSHEET:
        _fail("invalid-worksheet-root", part.value, "root", str(root.tag))
    return root


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


def _declares_xml_encoding(payload: bytes) -> bool:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    return _XML_DECLARATION_ENCODING.match(candidate) is not None


def _x14_hard_stop(root: ET.Element, part: CanonicalPartURI) -> None:
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith(f"{{{_X14}}}") and _local(element.tag) in _X14_LOCALS:
            _fail("unsupported_x14_content", part.value, "tag", element.tag)


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
    """Validate only placement and namespace of CF tags this reader owns."""
    for parent in root.iter():
        parent_is_root = parent is root
        parent_is_container = parent.tag == _CONTAINER and parent in tuple(root)
        for child in parent:
            local = _local(child.tag)
            if child.tag in {_CONTAINER, _RULE}:
                valid = (child.tag == _CONTAINER and parent_is_root) or (
                    child.tag == _RULE and parent_is_container
                )
                if not valid:
                    _fail("invalid-owned-native-cf-parent", part.value, "tag", str(child.tag))
                continue
            if local not in _OWNED_LOCALS:
                continue
            if parent_is_root or parent_is_container:
                _fail("owned-native-cf-namespace-collision", part.value, "tag", str(child.tag))

    for container in root:
        if container.tag == _CONTAINER:
            _owned_mixed(container, part)
            for rule in container:
                if rule.tag == _RULE:
                    _owned_mixed(rule, part)


def _presence(root: ET.Element) -> bool:
    return any(child.tag == _CONTAINER for child in root)


def _boolean(value: str, part: str, field: str) -> bool:
    result = _BOOLEANS.get(value)
    if result is None and value not in _BOOLEANS:
        _fail("invalid-native-cf-boolean", part, field, value)
    return result


def _a1_endpoint(value: str, part: str, sqref: str) -> tuple[str, int, int]:
    match = _CELL.fullmatch(value)
    if match is None:
        _fail("invalid-native-cf-sqref", part, "sqref", sqref)
    column_text, row_text = match.groups()
    column = 0
    for character in column_text.upper():
        column = column * 26 + ord(character) - ord("A") + 1
    row = int(row_text)
    if column > _MAX_COLUMN or row > _MAX_ROW:
        _fail("invalid-native-cf-sqref", part, "sqref", sqref)
    return (f"{column_text.upper()}{row}", row, column)


def _sqref(value: str | None, part: str) -> tuple[NativeCfA1Range, ...]:
    text = value or ""
    token_text = text.strip(_XML_WHITESPACE)
    if not token_text:
        _fail("invalid-native-cf-sqref", part, "sqref", text)
    tokens = tuple(re.split(r"[ \t\r\n]+", token_text))

    rectangles: list[tuple[int, int, int, int]] = []
    lexical_tokens: set[str] = set()
    canonical_rectangles: set[tuple[int, int, int, int]] = set()
    ranges: list[NativeCfA1Range] = []
    for token in tokens:
        endpoints = token.split(":")
        if len(endpoints) not in {1, 2}:
            _fail("invalid-native-cf-sqref", part, "sqref", text)
        start_coordinate, min_row, min_column = _a1_endpoint(endpoints[0], part, text)
        end_coordinate, max_row, max_column = _a1_endpoint(endpoints[-1], part, text)
        if min_row > max_row or min_column > max_column:
            _fail("invalid-native-cf-sqref", part, "sqref", text)
        rectangle = (min_row, min_column, max_row, max_column)
        if token in lexical_tokens or rectangle in canonical_rectangles:
            _fail("duplicate-native-cf-sqref", part, "sqref", token)
        if any(
            not (
                rectangle[2] < prior[0]
                or prior[2] < rectangle[0]
                or rectangle[3] < prior[1]
                or prior[3] < rectangle[1]
            )
            for prior in rectangles
        ):
            _fail("overlapping-native-cf-sqref", part, "sqref", token)
        lexical_tokens.add(token)
        canonical_rectangles.add(rectangle)
        rectangles.append(rectangle)
        ranges.append(NativeCfA1Range(
            start_coordinate,
            end_coordinate,
            min_row,
            min_column,
            max_row,
            max_column,
        ))
    return tuple(ranges)


def _container_attributes(container: ET.Element, part: CanonicalPartURI) -> tuple[tuple[NativeCfA1Range, ...], bool | None, str | None]:
    allowed = {"sqref", "pivot", f"{{{_XR}}}uid"}
    unknown = sorted(set(container.attrib) - allowed)
    if unknown:
        _fail("unknown-native-cf-attribute", part.value, "attribute", unknown[0])
    if "sqref" not in container.attrib:
        _fail("missing-native-cf-attribute", part.value, "attribute", "sqref")
    sqref = _sqref(container.attrib["sqref"], part.value)
    pivot = (
        _boolean(container.attrib["pivot"], part.value, "pivot")
        if "pivot" in container.attrib
        else None
    )
    uid = container.attrib.get(f"{{{_XR}}}uid")
    if uid is not None and (_GUID.fullmatch(uid) is None or not _nonwhite(uid)):
        _fail("invalid-native-cf-uid", part.value, "uid", uid)
    return (sqref, pivot, uid)


def _decoded_xml_for_attribute_scan(payload: bytes) -> str | None:
    if payload.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encoding = "utf-32"
    elif payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    elif payload.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    else:
        encoding = "utf-8"
    try:
        return payload.decode(encoding)
    except UnicodeError:
        return None


def _start_tags(text: str):
    """Yield element name and raw attribute text without interpreting XML data."""
    position = 0
    while position < len(text):
        start = text.find("<", position)
        if start < 0:
            return
        if text.startswith("<!--", start):
            end = text.find("-->", start + 4)
            if end < 0:
                return
            position = end + 3
            continue
        if text.startswith("<![CDATA[", start):
            end = text.find("]]>", start + 9)
            if end < 0:
                return
            position = end + 3
            continue
        if text.startswith("<?", start):
            end = text.find("?>", start + 2)
            if end < 0:
                return
            position = end + 2
            continue
        if text.startswith("</", start) or text.startswith("<!", start):
            position = start + 2
            continue
        name_match = _XML_NAME.match(text, start + 1)
        if name_match is None:
            position = start + 1
            continue
        cursor = name_match.end()
        quote: str | None = None
        while cursor < len(text):
            character = text[cursor]
            if quote is not None:
                if character == quote:
                    quote = None
            elif character in {"'", '"'}:
                quote = character
            elif character == ">":
                yield name_match.group(), text[name_match.end():cursor]
                cursor += 1
                break
            cursor += 1
        position = cursor


def _attribute_names(raw: str) -> tuple[str, ...] | None:
    names: list[str] = []
    position = 0
    while position < len(raw):
        while position < len(raw) and raw[position] in _XML_WHITESPACE:
            position += 1
        if position == len(raw) or raw[position] == "/":
            return tuple(names)
        name_match = _XML_NAME.match(raw, position)
        if name_match is None:
            return None
        names.append(name_match.group())
        position = name_match.end()
        while position < len(raw) and raw[position] in _XML_WHITESPACE:
            position += 1
        if position == len(raw) or raw[position] != "=":
            return None
        position += 1
        while position < len(raw) and raw[position] in _XML_WHITESPACE:
            position += 1
        if position == len(raw) or raw[position] not in {"'", '"'}:
            return None
        quote = raw[position]
        position = raw.find(quote, position + 1)
        if position < 0:
            return None
        position += 1
    return tuple(names)


def _reject_duplicate_container_attributes(payload: bytes, part: CanonicalPartURI) -> None:
    text = _decoded_xml_for_attribute_scan(payload)
    if text is None:
        return
    for name, raw_attributes in _start_tags(text):
        if name.rsplit(":", 1)[-1] != "conditionalFormatting":
            continue
        names = _attribute_names(raw_attributes)
        if names is None:
            continue
        seen: set[str] = set()
        for attribute in names:
            if attribute in seen:
                _fail("duplicate-native-cf-attribute", part.value, "attribute", attribute)
            seen.add(attribute)


def _container_inventory(container: ET.Element, part: CanonicalPartURI, index: int) -> NativeCfContainerInventory:
    sqref, pivot, uid = _container_attributes(container, part)
    rule_count = 0
    for child in container:
        if child.tag == _RULE:
            rule_count += 1
            continue
        if child.tag == _EXT_LIST:
            _fail("unsupported_native_cf_extension", part.value, "tag", _EXT_LIST)
        _fail("invalid-native-cf-container-child", part.value, "tag", str(child.tag))
    return NativeCfContainerInventory(
        f"{part.value}/worksheet/conditionalFormatting[{index}]",
        sqref,
        pivot,
        uid,
        rule_count,
    )


def _inventory(root: ET.Element, part: CanonicalPartURI) -> tuple[NativeCfContainerInventory, ...]:
    containers: list[NativeCfContainerInventory] = []
    for child in root:
        if child.tag == _CONTAINER:
            containers.append(_container_inventory(child, part, len(containers) + 1))
    return tuple(containers)


def read_worksheet_native_cf_presence(package_path: os.PathLike[str] | str) -> WorkbookNativeCfPresence:
    """Inventory native CF container presence; never parse semantic CF content."""
    path = _coerce_package_path(package_path)
    topology = read_workbook_topology(path)
    records = []
    for worksheet in topology.worksheets:
        part = worksheet.worksheet_part
        root = _xml(_member(path, part), part)
        _x14_hard_stop(root, part)
        _validate_owned_placement(root, part)
        records.append(WorksheetNativeCfPresence(worksheet, _presence(root)))
    return WorkbookNativeCfPresence(tuple(records))


def read_worksheet_native_cf_container_inventory(
    package_path: os.PathLike[str] | str,
) -> WorkbookNativeCfContainerInventory:
    """Inventory native CF containers and A1 geometry; never parse rule semantics."""
    path = _coerce_package_path(package_path)
    topology = read_workbook_topology(path)
    records = []
    for worksheet in topology.worksheets:
        part = worksheet.worksheet_part
        payload = _member(path, part)
        _reject_duplicate_container_attributes(payload, part)
        root = _xml(payload, part)
        _x14_hard_stop(root, part)
        _validate_owned_placement(root, part)
        records.append(WorksheetNativeCfContainerInventory(worksheet, _inventory(root, part)))
    return WorkbookNativeCfContainerInventory(tuple(records))
