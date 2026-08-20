"""Strict, read-only SpreadsheetML workbook defined-name semantics."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology
from .opc_worksheet_structure_reader import A1Range


_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_WORKBOOK: Final = f"{{{_SML}}}workbook"
_DEFINED_NAMES: Final = f"{{{_SML}}}definedNames"
_DEFINED_NAME: Final = f"{{{_SML}}}definedName"
_OWNED_LOCALS: Final = frozenset({"definedNames", "definedName"})
_XML_DECLARATION_ENCODING: Final = re.compile(
    br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']', re.IGNORECASE,
)
_XML_WHITESPACE: Final = re.compile(r"[\t\r\n ]+")
_NONNEGATIVE_INTEGER: Final = re.compile(r"\+?[0-9]+\Z")
_A1: Final = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})\Z")
_UNQUOTED_SHEET: Final = re.compile(r"[A-Za-z_\u0080-\U0010ffff][A-Za-z0-9_.\u0080-\U0010ffff]*\Z")
_MAX_ROW: Final = 1_048_576
_MAX_COLUMN: Final = 16_384
_MAX_UNSIGNED: Final = 4_294_967_295
_MAX_FILTER_EXPRESSION_LENGTH: Final = 32_767
_FILTER_DATABASE: Final = "_xlnm._FilterDatabase"
_RANGE_OWNING_BUILT_INS: Final = frozenset({
    "_xlnm.Print_Area", "_xlnm.Print_Titles", "_xlnm.Criteria", "_xlnm.Extract",
    "_xlnm.Database", "_xlnm.Consolidate_Area", "_xlnm.Sheet_Title",
})
_DEFINED_NAME_ATTRIBUTES: Final = frozenset({
    "name", "comment", "customMenu", "description", "help", "statusBar",
    "localSheetId", "hidden", "function", "vbProcedure", "xlm",
    "functionGroupId", "shortcutKey", "publishToServer", "workbookParameter",
})
_XML_BOOLEANS: Final = {"0": False, "1": True, "false": False, "true": True}
_BOOLEAN_ATTRIBUTES: Final = (
    "hidden", "function", "vbProcedure", "xlm", "publishToServer", "workbookParameter",
)


@dataclass(frozen=True)
class WorkbookDefinedName:
    name: str
    local_sheet_index: int | None
    hidden: bool | None
    expression: str


@dataclass(frozen=True)
class WorkbookFilterDatabase:
    worksheet: WorksheetDescriptor
    reference: A1Range


@dataclass(frozen=True)
class WorkbookDefinedNameSemantics:
    defined_names: tuple[WorkbookDefinedName, ...]
    filter_databases: tuple[WorkbookFilterDatabase, ...]


@dataclass
class OPCWorkbookDefinedNameReaderError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorkbookDefinedNameReaderError(code, subject, field, detail)


def _coerce_package_path(package_path: os.PathLike[str] | str) -> str:
    kind = type(package_path)
    subject = f"{kind.__module__}.{kind.__qualname__}"
    try:
        path = os.fspath(package_path)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except (ValueError, OSError) as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    except Exception as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str):
        _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path:
        _fail("unreadable-package", path, "path", "embedded-nul")
    return path


def _read_workbook_member(path: str, part: CanonicalPartURI) -> bytes:
    """Read precisely the topology-owned canonical workbook ZIP member."""
    try:
        with ZipFile(path) as archive:
            matches = []
            for info in archive.infolist():
                try:
                    canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError:
                    _fail("unreadable-workbook-part", part.value, "member", "invalid-member-name")
                if canonical == part:
                    if info.filename != part.value:
                        _fail("noncanonical-workbook-member", part.value, "member", info.filename)
                    matches.append(info)
            if not matches:
                _fail("missing-workbook-member", part.value, "member", part.value)
            if len(matches) != 1:
                _fail("ambiguous-workbook-member", part.value, "member", part.value)
            return archive.read(matches[0])
    except OPCWorkbookDefinedNameReaderError:
        raise
    except (BadZipFile, LargeZipFile, EOFError, KeyError, NotImplementedError, OSError, RuntimeError, ValueError) as error:
        _fail("unreadable-workbook-part", part.value, "member", type(error).__name__)
    raise AssertionError("unreachable")


def _parse_workbook_xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    if _XML_DECLARATION_ENCODING.match(candidate) is not None:
        try:
            ET.fromstring(payload)
        except (LookupError, ValueError):
            _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    try:
        root = ET.fromstring(payload)
    except LookupError:
        _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except (ET.ParseError, UnicodeError, ValueError, TypeError):
        _fail("malformed-workbook-xml", part.value, "xml", "xml")
    if root.tag != _WORKBOOK:
        _fail("invalid-workbook-root", part.value, "root", str(root.tag))
    return root


def _non_whitespace(value: str | None) -> bool:
    return bool(value and not value.isspace())


def _owned_tag_checks(root: ET.Element, part: CanonicalPartURI) -> tuple[ET.Element | None, dict[int, ET.Element]]:
    """Reject namespace collisions and owned nodes outside their only legal tree."""
    parents = {id(child): parent for parent in root.iter() for child in parent}
    container: ET.Element | None = None
    for element in root.iter():
        tag = element.tag
        if not isinstance(tag, str):
            continue
        local = tag.rsplit("}", 1)[-1]
        if local not in _OWNED_LOCALS:
            continue
        expected = _DEFINED_NAMES if local == "definedNames" else _DEFINED_NAME
        if tag != expected:
            _fail("owned-defined-name-namespace-collision", part.value, "tag", str(tag))
        parent = parents.get(id(element))
        if tag == _DEFINED_NAMES:
            if parent is not root:
                _fail("invalid-owned-defined-name-parent", part.value, "tag", str(tag))
            if container is not None:
                _fail("duplicate-defined-names", part.value, "definedNames", "")
            container = element
        elif parent is not container:
            _fail("invalid-owned-defined-name-parent", part.value, "tag", str(tag))
    return container, parents


def _unsigned_integer(value: str, part: str, field: str, code: str) -> int:
    """Read a bounded XML-whitespace non-negative integer without coercion."""
    lexical = _XML_WHITESPACE.sub(" ", value).strip(" ")
    digits = lexical.removeprefix("+")
    if _NONNEGATIVE_INTEGER.fullmatch(lexical) is None or len(digits) > 10:
        _fail(code, part, field, value)
    number = int(lexical)
    if number > _MAX_UNSIGNED:
        _fail(code, part, field, value)
    return number


def _local_sheet_index(value: str | None, part: str, worksheet_count: int) -> int | None:
    if value is None:
        return None
    index = _unsigned_integer(value, part, "localSheetId", "invalid-local-sheet-index")
    if index >= worksheet_count:
        _fail("invalid-local-sheet-index", part, "localSheetId", value)
    return index


def _hidden(value: str | None, part: str) -> bool | None:
    if value is None:
        return None
    if value not in _XML_BOOLEANS:
        _fail("invalid-defined-name-hidden", part, "hidden", value)
    return _XML_BOOLEANS[value]


def _boolean_attribute(value: str, part: str, field: str) -> None:
    if value not in _XML_BOOLEANS:
        _fail("invalid-defined-name-boolean", part, field, value)


def _validate_native_attributes(element: ET.Element, part: str) -> None:
    """Validate every accepted non-opaque lexical type before semantic mapping."""
    for field in _BOOLEAN_ATTRIBUTES:
        if field == "hidden":
            continue
        if field in element.attrib:
            _boolean_attribute(element.attrib[field], part, field)
    if "functionGroupId" in element.attrib:
        _unsigned_integer(
            element.attrib["functionGroupId"], part, "functionGroupId", "invalid-defined-name-function-group-id",
        )


def _range(value: str, part: str) -> A1Range:
    pieces = value.split(":")
    if len(pieces) not in {1, 2} or not value:
        _fail("invalid-filter-database-reference", part, "expression", value)
    points: list[tuple[int, int, str]] = []
    for piece in pieces:
        match = _A1.fullmatch(piece)
        if match is None:
            _fail("invalid-filter-database-reference", part, "expression", value)
        column = 0
        for character in match.group(1).upper():
            column = column * 26 + ord(character) - ord("A") + 1
        row = int(match.group(2))
        if column > _MAX_COLUMN or row > _MAX_ROW:
            _fail("invalid-filter-database-reference", part, "expression", value)
        points.append((row, column, f"{match.group(1).upper()}{row}"))
    first, last = points[0], points[-1]
    if first[0] > last[0] or first[1] > last[1]:
        _fail("invalid-filter-database-reference", part, "expression", value)
    return A1Range(first[2], last[2], first[0], last[0], first[1], last[1])


def _filter_database_reference(expression: str, worksheet: WorksheetDescriptor, part: str) -> A1Range:
    if not expression or len(expression) > _MAX_FILTER_EXPRESSION_LENGTH:
        _fail("invalid-filter-database-expression", part, "expression", expression)
    delimiters: list[int] = []
    quoted = False
    position = 0
    while position < len(expression):
        character = expression[position]
        if character == "'":
            if quoted and position + 1 < len(expression) and expression[position + 1] == "'":
                position += 2
                continue
            quoted = not quoted
        elif character == "!" and not quoted:
            delimiters.append(position)
        position += 1
    if quoted or len(delimiters) != 1:
        _fail("invalid-filter-database-expression", part, "expression", expression)
    delimiter = delimiters[0]
    sheet_text, reference_text = expression[:delimiter], expression[delimiter + 1:]
    if sheet_text.startswith("'"):
        if len(sheet_text) < 2 or not sheet_text.endswith("'"):
            _fail("invalid-filter-database-expression", part, "expression", expression)
        inner = sheet_text[1:-1]
        if "'" in inner.replace("''", ""):
            _fail("invalid-filter-database-expression", part, "expression", expression)
        sheet_name = inner.replace("''", "'")
    else:
        if _UNQUOTED_SHEET.fullmatch(sheet_text) is None:
            _fail("invalid-filter-database-expression", part, "expression", expression)
        sheet_name = sheet_text
    if sheet_name != worksheet.name:
        _fail("filter-database-sheet-mismatch", part, "expression", expression)
    return _range(reference_text, part)


def _defined_name(
    element: ET.Element, part: str, worksheets: tuple[WorksheetDescriptor, ...],
) -> WorkbookDefinedName:
    unknown = sorted(set(element.attrib) - _DEFINED_NAME_ATTRIBUTES)
    if unknown:
        _fail("unknown-defined-name-attribute", part, "attribute", unknown[0])
    if len(element):
        _fail("invalid-defined-name-content", part, "definedName", "nested")
    if _non_whitespace(element.tail):
        _fail("invalid-defined-names-content", part, "definedNames", "tail")
    name = element.attrib.get("name")
    if name is None:
        _fail("missing-defined-name-attribute", part, "attribute", "name")
    if not name.strip():
        _fail("blank-defined-name", part, "name", name)
    local_sheet_index = _local_sheet_index(element.attrib.get("localSheetId"), part, len(worksheets))
    hidden = _hidden(element.attrib.get("hidden"), part)
    _validate_native_attributes(element, part)
    expression = element.text or ""
    return WorkbookDefinedName(name, local_sheet_index, hidden, expression)


def _semantics(root: ET.Element, part: CanonicalPartURI, worksheets: tuple[WorksheetDescriptor, ...]) -> WorkbookDefinedNameSemantics:
    container, _parents = _owned_tag_checks(root, part)
    if container is None:
        return WorkbookDefinedNameSemantics((), ())
    if container.attrib:
        _fail("unknown-defined-names-attribute", part.value, "attribute", sorted(container.attrib)[0])
    if _non_whitespace(container.text):
        _fail("invalid-defined-names-content", part.value, "definedNames", "text")
    if _non_whitespace(container.tail):
        _fail("invalid-defined-names-content", part.value, "definedNames", "tail")
    names: list[WorkbookDefinedName] = []
    seen_names: set[tuple[str, int | None]] = set()
    filter_databases: list[WorkbookFilterDatabase] = []
    filter_scopes: set[int] = set()
    for element in container:
        if element.tag != _DEFINED_NAME:
            _fail("invalid-defined-names-child", part.value, "tag", str(element.tag))
        record = _defined_name(element, part.value, worksheets)
        names.append(record)
        if record.name == _FILTER_DATABASE:
            if record.local_sheet_index is None:
                _fail("missing-filter-database-scope", part.value, "localSheetId", "")
            if record.local_sheet_index in filter_scopes:
                _fail("duplicate-filter-database-scope", part.value, "localSheetId", str(record.local_sheet_index))
            filter_scopes.add(record.local_sheet_index)
            worksheet = worksheets[record.local_sheet_index]
            reference = _filter_database_reference(record.expression, worksheet, part.value)
            filter_databases.append(WorkbookFilterDatabase(worksheet, reference))
            continue
        if record.name in _RANGE_OWNING_BUILT_INS:
            _fail("unsupported-range-owning-built-in", part.value, "name", record.name)
        scope = (record.name.casefold(), record.local_sheet_index)
        if scope in seen_names:
            _fail("duplicate-defined-name", part.value, "name", record.name)
        seen_names.add(scope)
    return WorkbookDefinedNameSemantics(tuple(names), tuple(filter_databases))


def read_workbook_defined_name_semantics(package_path: os.PathLike[str] | str) -> WorkbookDefinedNameSemantics:
    """Return opaque names plus the strictly validated FilterDatabase projection."""
    path = _coerce_package_path(package_path)
    topology = read_workbook_topology(path)
    payload = _read_workbook_member(path, topology.workbook_part)
    root = _parse_workbook_xml(payload, topology.workbook_part)
    return _semantics(root, topology.workbook_part, topology.worksheets)
