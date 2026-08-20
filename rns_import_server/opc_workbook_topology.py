"""Strict, read-only SpreadsheetML workbook topology discovery."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile

from .opc_package_graph import (
    OPCPackageGraphError,
    PackageRelationship,
    build_opc_package_graph,
)
from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri


_SPREADSHEETML_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WORKBOOK_TAG: Final = f"{{{_SPREADSHEETML_NS}}}workbook"
_SHEETS_TAG: Final = f"{{{_SPREADSHEETML_NS}}}sheets"
_SHEET_TAG: Final = f"{{{_SPREADSHEETML_NS}}}sheet"
_RELATIONSHIP_ID: Final = f"{{{_OFFICE_REL_NS}}}id"
_OFFICE_DOCUMENT: Final = f"{_OFFICE_REL_NS}/officeDocument"
_WORKSHEET: Final = f"{_OFFICE_REL_NS}/worksheet"
_CONTENT_TYPES_NS: Final = "http://schemas.openxmlformats.org/package/2006/content-types"
_TYPES_TAG: Final = f"{{{_CONTENT_TYPES_NS}}}Types"
_OVERRIDE_TAG: Final = f"{{{_CONTENT_TYPES_NS}}}Override"
_MAIN_WORKBOOK_CONTENT_TYPES: Final = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
})
_XML_DECLARATION_ENCODING: Final = re.compile(
    br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_SHEET_ID: Final = re.compile(r"\+?[0-9]+\Z")
_MAX_SHEET_ID: Final = 4_294_967_295
_SHEET_ATTRIBUTES: Final = frozenset({"name", "sheetId", "state", _RELATIONSHIP_ID})
_SHEET_STATES: Final = frozenset({"visible", "hidden", "veryHidden"})


@dataclass(frozen=True)
class WorksheetDescriptor:
    name: str
    sheet_id: int
    state: str
    relationship_id: str
    worksheet_part: CanonicalPartURI


@dataclass(frozen=True)
class WorkbookTopology:
    workbook_part: CanonicalPartURI
    worksheets: tuple[WorksheetDescriptor, ...]


@dataclass
class OPCWorkbookTopologyError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorkbookTopologyError(code, subject, field, detail)


def _coerce_package_path(package_path: os.PathLike[str] | str) -> str:
    path_type = type(package_path)
    subject = f"{path_type.__module__}.{path_type.__qualname__}"
    try:
        value = os.fspath(package_path)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except (ValueError, OSError) as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(value, str):
        _fail("invalid-package-path", subject, "path", type(value).__name__)
    if "\x00" in value:
        _fail("unreadable-package", value, "path", "embedded-nul")
    return value


def _read_required_xml(package_path: str, workbook_part: CanonicalPartURI) -> tuple[bytes, bytes]:
    try:
        with ZipFile(package_path) as package:
            workbook_info = next(
                (info for info in package.infolist() if canonicalize_part_uri(info.filename) == workbook_part), None,
            )
            if workbook_info is None:
                _fail("unreadable-workbook-part", workbook_part.value, "xml", "missing")
            return package.read(workbook_info), package.read("[Content_Types].xml")
    except OPCPartURIError as error:
        _fail("unreadable-workbook-part", workbook_part.value, "xml", error.code)
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error:
        _fail("unreadable-workbook-part", workbook_part.value, "xml", type(error).__name__)
    raise AssertionError("unreachable")


def _override_part_name(value: str) -> CanonicalPartURI | None:
    if not value.startswith("/"):
        return None
    try:
        return canonicalize_part_uri(value[1:])
    except OPCPartURIError:
        return None


def _require_main_workbook_content_type(payload: bytes, workbook_part: CanonicalPartURI) -> None:
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, LookupError, UnicodeError, ValueError):
        _fail("unreadable-workbook-content-type", workbook_part.value, "content-type", "xml")
    if root.tag != _TYPES_TAG:
        _fail("unreadable-workbook-content-type", workbook_part.value, "content-type", "root")
    expected_part_name = f"/{workbook_part.value}"
    values = tuple(
        child.attrib.get("ContentType", "")
        for child in root
        if child.tag == _OVERRIDE_TAG and _override_part_name(child.attrib.get("PartName", "")) == workbook_part
    )
    if not values:
        _fail("missing-workbook-content-type", workbook_part.value, "PartName", expected_part_name)
    if len(values) != 1:
        _fail("ambiguous-workbook-content-type", workbook_part.value, "PartName", expected_part_name)
    if values[0] not in _MAIN_WORKBOOK_CONTENT_TYPES:
        _fail("unsupported-workbook-content-type", workbook_part.value, "ContentType", values[0])


def _parse_workbook_xml(payload: bytes, workbook_part: CanonicalPartURI) -> ET.Element:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    match = _XML_DECLARATION_ENCODING.match(candidate)
    if match is not None:
        try:
            ET.fromstring(payload)
        except (LookupError, ValueError):
            _fail("unsupported-xml-encoding", workbook_part.value, "xml", "encoding")
    try:
        root = ET.fromstring(payload)
    except LookupError:
        _fail("unsupported-xml-encoding", workbook_part.value, "xml", "encoding")
    except (ET.ParseError, UnicodeError, ValueError):
        _fail("malformed-workbook-xml", workbook_part.value, "xml", "xml")
    if root.tag != _WORKBOOK_TAG:
        _fail("invalid-workbook-root", workbook_part.value, "root", str(root.tag))
    return root


def _workbook_part(relationships: tuple[PackageRelationship, ...]) -> CanonicalPartURI:
    matches = tuple(item for item in relationships if item.source is None and item.type_uri == _OFFICE_DOCUMENT)
    if not matches:
        _fail("missing-workbook-relationship", "_rels/.rels", "Type", _OFFICE_DOCUMENT)
    if len(matches) != 1:
        _fail("ambiguous-workbook-relationship", "_rels/.rels", "Type", _OFFICE_DOCUMENT)
    relationship = matches[0]
    if relationship.target_mode != "Internal":
        _fail("external-workbook-relationship", "_rels/.rels", "TargetMode", relationship.target_mode)
    if relationship.resolved_target is None:
        _fail("dangling-workbook-relationship", "_rels/.rels", "Target", relationship.target)
    return relationship.resolved_target


def _sheets_element(root: ET.Element, workbook_part: CanonicalPartURI) -> ET.Element:
    sheets = tuple(child for child in root if child.tag == _SHEETS_TAG)
    if not sheets:
        _fail("missing-sheets", workbook_part.value, "sheets", "")
    if len(sheets) != 1:
        _fail("duplicate-sheets", workbook_part.value, "sheets", "")
    return sheets[0]


def _relationship_for_sheet(
    relationships: tuple[PackageRelationship, ...], workbook_part: CanonicalPartURI, relationship_id: str,
) -> PackageRelationship:
    matches = tuple(item for item in relationships if item.source == workbook_part and item.id == relationship_id)
    if not matches:
        _fail("missing-sheet-relationship", workbook_part.value, "r:id", relationship_id)
    if len(matches) != 1:
        _fail("ambiguous-sheet-relationship", workbook_part.value, "r:id", relationship_id)
    relationship = matches[0]
    if relationship.target_mode != "Internal":
        _fail("external-sheet-relationship", workbook_part.value, "r:id", relationship_id)
    if relationship.type_uri != _WORKSHEET:
        _fail("non-worksheet-relationship", workbook_part.value, "r:id", relationship_id)
    if relationship.resolved_target is None:
        _fail("dangling-sheet-relationship", workbook_part.value, "r:id", relationship_id)
    return relationship


def _descriptor(
    element: ET.Element, relationships: tuple[PackageRelationship, ...], workbook_part: CanonicalPartURI,
    names: set[str], sheet_ids: set[int], relationship_ids: set[str], worksheet_parts: set[CanonicalPartURI],
) -> WorksheetDescriptor:
    unknown = sorted(set(element.attrib) - _SHEET_ATTRIBUTES)
    if unknown:
        _fail("unknown-sheet-attribute", workbook_part.value, "attribute", unknown[0])
    for attribute in ("name", "sheetId", _RELATIONSHIP_ID):
        if attribute not in element.attrib:
            _fail("missing-sheet-attribute", workbook_part.value, "attribute", attribute)
        if not element.attrib[attribute].strip():
            _fail("blank-sheet-attribute", workbook_part.value, "attribute", attribute)
    name = element.attrib["name"]
    if name in names:
        _fail("duplicate-sheet-name", workbook_part.value, "name", name)
    sheet_id_text = element.attrib["sheetId"]
    if _SHEET_ID.fullmatch(sheet_id_text) is None:
        _fail("invalid-sheet-id", workbook_part.value, "sheetId", sheet_id_text)
    numeric_text = sheet_id_text.removeprefix("+").lstrip("0") or "0"
    if len(numeric_text) > 10:
        _fail("invalid-sheet-id", workbook_part.value, "sheetId", sheet_id_text)
    sheet_id = int(numeric_text)
    if sheet_id == 0 or sheet_id > _MAX_SHEET_ID:
        _fail("invalid-sheet-id", workbook_part.value, "sheetId", sheet_id_text)
    if sheet_id in sheet_ids:
        _fail("duplicate-sheet-id", workbook_part.value, "sheetId", sheet_id_text)
    relationship_id = element.attrib[_RELATIONSHIP_ID]
    if relationship_id in relationship_ids:
        _fail("duplicate-sheet-relationship-id", workbook_part.value, "r:id", relationship_id)
    state = element.attrib.get("state", "visible")
    if state not in _SHEET_STATES:
        _fail("invalid-sheet-state", workbook_part.value, "state", state)
    relationship = _relationship_for_sheet(relationships, workbook_part, relationship_id)
    if relationship.resolved_target in worksheet_parts:
        _fail("duplicate-sheet-target", workbook_part.value, "r:id", relationship_id)
    names.add(name); sheet_ids.add(sheet_id); relationship_ids.add(relationship_id); worksheet_parts.add(relationship.resolved_target)
    return WorksheetDescriptor(name, sheet_id, state, relationship_id, relationship.resolved_target)


def read_workbook_topology(package_path: os.PathLike[str] | str) -> WorkbookTopology:
    """Return the immutable worksheet topology, or one typed stable failure."""
    path = _coerce_package_path(package_path)
    try:
        graph = build_opc_package_graph(path)
    except OPCPackageGraphError as error:
        _fail(error.code, error.subject, error.field, error.detail)
    workbook_part = _workbook_part(graph.relationships)
    workbook_xml, content_types_xml = _read_required_xml(path, workbook_part)
    _require_main_workbook_content_type(content_types_xml, workbook_part)
    root = _parse_workbook_xml(workbook_xml, workbook_part)
    sheets = _sheets_element(root, workbook_part)
    names: set[str] = set(); sheet_ids: set[int] = set(); relationship_ids: set[str] = set(); worksheet_parts: set[CanonicalPartURI] = set()
    descriptors: list[WorksheetDescriptor] = []
    for element in sheets:
        if element.tag != _SHEET_TAG:
            _fail("invalid-sheets-child", workbook_part.value, "tag", str(element.tag))
        descriptors.append(_descriptor(element, graph.relationships, workbook_part, names, sheet_ids, relationship_ids, worksheet_parts))
    return WorkbookTopology(workbook_part, tuple(descriptors))
