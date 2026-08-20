"""Strict, immutable SpreadsheetML cell and hyperlink reader."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile

from .opc_package_graph import OPCPackageGraphError, PackageRelationship, build_opc_package_graph
from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import OPCWorkbookTopologyError, WorksheetDescriptor, read_workbook_topology


_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WORKSHEET: Final = f"{{{_SML}}}worksheet"
_SHEET_DATA: Final = f"{{{_SML}}}sheetData"
_ROW: Final = f"{{{_SML}}}row"
_CELL: Final = f"{{{_SML}}}c"
_VALUE: Final = f"{{{_SML}}}v"
_FORMULA: Final = f"{{{_SML}}}f"
_INLINE_STRING: Final = f"{{{_SML}}}is"
_TEXT: Final = f"{{{_SML}}}t"
_HYPERLINKS: Final = f"{{{_SML}}}hyperlinks"
_HYPERLINK: Final = f"{{{_SML}}}hyperlink"
_REL_ID: Final = f"{{{_REL}}}id"
_HYPERLINK_TYPE: Final = f"{_REL}/hyperlink"
_XML_ENCODING: Final = re.compile(br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']', re.I)
_A1: Final = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})\Z")
_INDEX: Final = re.compile(r"[0-9]+\Z")
_MAX_ROW: Final = 1_048_576
_MAX_COLUMN: Final = 16_384
_CELL_TYPES: Final = frozenset({"", "b", "d", "e", "inlineStr", "s", "str"})


@dataclass(frozen=True)
class CellFormula:
    text: str
    kind: str
    shared_index: int | None
    reference: str | None


@dataclass(frozen=True)
class WorksheetCell:
    coordinate: str
    row: int
    column: int
    cell_type: str
    value: str | None
    inline_text: str | None
    shared_string_index: int | None
    formula: CellFormula | None


@dataclass(frozen=True)
class WorksheetHyperlink:
    ref: str
    relationship_id: str | None
    location: str | None
    display: str | None
    tooltip: str | None
    target_mode: str | None
    target: str | None
    resolved_target: CanonicalPartURI | None


@dataclass(frozen=True)
class WorksheetCells:
    worksheet: WorksheetDescriptor
    cells: tuple[WorksheetCell, ...]
    hyperlinks: tuple[WorksheetHyperlink, ...]


@dataclass(frozen=True)
class WorkbookCellSemantics:
    worksheets: tuple[WorksheetCells, ...]


@dataclass
class OPCWorksheetCellReaderError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetCellReaderError(code, subject, field, detail)


def _coerce_package_path(package_path: os.PathLike[str] | str) -> str:
    kind = type(package_path)
    subject = f"{kind.__module__}.{kind.__qualname__}"
    try:
        path = os.fspath(package_path)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except (ValueError, OSError) as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str):
        _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path:
        _fail("unreadable-package", path, "path", "embedded-nul")
    return path


def _a1(value: str, subject: str, field: str, *, range_allowed: bool = False) -> tuple[int, int]:
    pieces = value.split(":")
    if (len(pieces) != 1 and (not range_allowed or len(pieces) != 2)) or not value:
        _fail("invalid-a1-reference", subject, field, value)
    parsed: list[tuple[int, int]] = []
    for piece in pieces:
        match = _A1.fullmatch(piece)
        if match is None:
            _fail("invalid-a1-reference", subject, field, value)
        column = 0
        for char in match.group(1).upper():
            column = column * 26 + ord(char) - ord("A") + 1
        row = int(match.group(2))
        if column > _MAX_COLUMN or row > _MAX_ROW:
            _fail("invalid-a1-reference", subject, field, value)
        parsed.append((row, column))
    if len(parsed) == 2 and parsed[0] > parsed[1]:
        _fail("invalid-a1-reference", subject, field, value)
    return parsed[0]


def _parse_xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    if _XML_ENCODING.match(candidate) is not None:
        try:
            ET.fromstring(payload)
        except (LookupError, ValueError):
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


def _read_part(path: str, part: CanonicalPartURI) -> bytes:
    try:
        with ZipFile(path) as package:
            matches = []
            for info in package.infolist():
                try:
                    canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError:
                    _fail("unreadable-worksheet-part", part.value, "xml", "invalid-member-name")
                if canonical == part:
                    matches.append(info)
            if len(matches) != 1:
                _fail("ambiguous-worksheet-member" if matches else "missing-worksheet-member", part.value, "member", part.value)
            return package.read(matches[0])
    except OPCWorksheetCellReaderError:
        raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error:
        _fail("unreadable-worksheet-part", part.value, "xml", type(error).__name__)
    raise AssertionError("unreachable")


def _only_text(element: ET.Element, part: CanonicalPartURI, field: str) -> str:
    if element.attrib or len(element) or (element.text is None):
        _fail("invalid-inline-string", part.value, field, "structure")
    return element.text


def _formula(element: ET.Element, part: CanonicalPartURI) -> CellFormula:
    if set(element.attrib) - {"t", "si", "ref"} or len(element):
        _fail("invalid-formula", part.value, "f", "structure")
    kind = element.attrib.get("t", "normal")
    if kind not in {"normal", "shared", "array"}:
        _fail("unsupported-formula-kind", part.value, "t", kind)
    shared = element.attrib.get("si")
    reference = element.attrib.get("ref")
    if kind == "shared":
        if shared is None or _INDEX.fullmatch(shared) is None:
            _fail("invalid-shared-formula-index", part.value, "si", shared or "")
    elif shared is not None:
        _fail("invalid-formula-attribute", part.value, "si", shared)
    if reference is not None:
        _a1(reference, part.value, "ref", range_allowed=True)
    return CellFormula(element.text or "", kind, int(shared) if shared is not None else None, reference)


def _cell(element: ET.Element, part: CanonicalPartURI, expected_row: int, previous: tuple[int, int] | None) -> tuple[WorksheetCell, tuple[int, int]]:
    if set(element.attrib) - {"r", "t"}:
        _fail("unknown-cell-attribute", part.value, "attribute", sorted(set(element.attrib) - {"r", "t"})[0])
    coordinate = element.attrib.get("r")
    if coordinate is None:
        _fail("missing-cell-coordinate", part.value, "r", "")
    row, column = _a1(coordinate, part.value, "r")
    if row != expected_row:
        _fail("cell-row-mismatch", part.value, "r", coordinate)
    current = (row, column)
    if previous is not None and current <= previous:
        _fail("out-of-order-cell", part.value, "r", coordinate)
    cell_type = element.attrib.get("t", "")
    if cell_type not in _CELL_TYPES:
        _fail("unsupported-cell-type", part.value, "t", cell_type)
    formula_element: ET.Element | None = None; value_element: ET.Element | None = None; inline_element: ET.Element | None = None
    allowed = {_FORMULA, _VALUE, _INLINE_STRING}
    for child in element:
        if child.tag not in allowed:
            _fail("invalid-cell-child", part.value, "tag", str(child.tag))
        if child.tag == _FORMULA:
            if formula_element is not None: _fail("duplicate-cell-payload", part.value, "f", "")
            formula_element = child
        elif child.tag == _VALUE:
            if value_element is not None: _fail("duplicate-cell-payload", part.value, "v", "")
            value_element = child
        else:
            if inline_element is not None: _fail("duplicate-cell-payload", part.value, "is", "")
            inline_element = child
    if element.text and not element.text.isspace(): _fail("invalid-cell-content", part.value, "text", coordinate)
    if cell_type == "inlineStr":
        if inline_element is None or value_element is not None:
            _fail("invalid-cell-payload", part.value, "t", cell_type)
    elif value_element is None or inline_element is not None:
        _fail("invalid-cell-payload", part.value, "t", cell_type)
    if value_element is not None and (value_element.attrib or len(value_element)):
        _fail("invalid-cell-value", part.value, "v", "structure")
    value = value_element.text if value_element is not None else None
    inline_text = None
    if inline_element is not None:
        if inline_element.attrib or len(inline_element) != 1 or inline_element[0].tag != _TEXT:
            _fail("invalid-inline-string", part.value, "is", "structure")
        inline_text = _only_text(inline_element[0], part, "is")
    shared_index = None
    if cell_type == "s":
        if value is None or _INDEX.fullmatch(value) is None:
            _fail("invalid-shared-string-index", part.value, "v", value or "")
        shared_index = int(value)
    formula = _formula(formula_element, part) if formula_element is not None else None
    return WorksheetCell(coordinate, row, column, cell_type, value, inline_text, shared_index, formula), current


def _cells(root: ET.Element, part: CanonicalPartURI) -> tuple[WorksheetCell, ...]:
    structures = tuple(child for child in root if child.tag == _SHEET_DATA)
    if len(structures) != 1:
        _fail("missing-sheet-data" if not structures else "duplicate-sheet-data", part.value, "sheetData", "")
    records: list[WorksheetCell] = []; previous_row = 0; seen: set[str] = set()
    for row_element in structures[0]:
        if row_element.tag != _ROW:
            _fail("invalid-sheet-data-child", part.value, "tag", str(row_element.tag))
        if set(row_element.attrib) - {"r"}: _fail("unknown-row-attribute", part.value, "attribute", sorted(set(row_element.attrib) - {"r"})[0])
        lexical = row_element.attrib.get("r", "")
        if _INDEX.fullmatch(lexical) is None or int(lexical) == 0 or int(lexical) > _MAX_ROW:
            _fail("invalid-row", part.value, "r", lexical)
        row = int(lexical)
        if row <= previous_row: _fail("out-of-order-row", part.value, "r", lexical)
        previous_row = row; prior: tuple[int, int] | None = None
        for cell_element in row_element:
            if cell_element.tag != _CELL: _fail("invalid-row-child", part.value, "tag", str(cell_element.tag))
            record, prior = _cell(cell_element, part, row, prior)
            if record.coordinate in seen: _fail("duplicate-cell-coordinate", part.value, "r", record.coordinate)
            seen.add(record.coordinate); records.append(record)
    return tuple(records)


def _hyperlinks(root: ET.Element, part: CanonicalPartURI, relationships: tuple[PackageRelationship, ...]) -> tuple[WorksheetHyperlink, ...]:
    containers = tuple(child for child in root if child.tag == _HYPERLINKS)
    if len(containers) > 1: _fail("duplicate-hyperlinks", part.value, "hyperlinks", "")
    if not containers: return ()
    records: list[WorksheetHyperlink] = []; refs: set[str] = set(); ids: set[str] = set()
    for element in containers[0]:
        if element.tag != _HYPERLINK: _fail("invalid-hyperlinks-child", part.value, "tag", str(element.tag))
        if set(element.attrib) - {"ref", _REL_ID, "location", "display", "tooltip"}:
            _fail("unknown-hyperlink-attribute", part.value, "attribute", sorted(set(element.attrib) - {"ref", _REL_ID, "location", "display", "tooltip"})[0])
        ref = element.attrib.get("ref", ""); _a1(ref, part.value, "ref", range_allowed=True)
        if ref in refs: _fail("duplicate-hyperlink-ref", part.value, "ref", ref)
        refs.add(ref)
        relationship_id = element.attrib.get(_REL_ID); location = element.attrib.get("location")
        if bool(relationship_id) == bool(location): _fail("invalid-hyperlink-anchor", part.value, "anchor", ref)
        for key in ("display", "tooltip"):
            if key in element.attrib and not element.attrib[key].strip(): _fail("blank-hyperlink-attribute", part.value, key, "")
        if location is not None and not location.strip(): _fail("blank-hyperlink-attribute", part.value, "location", "")
        if relationship_id is None:
            records.append(WorksheetHyperlink(ref, None, location, element.attrib.get("display"), element.attrib.get("tooltip"), None, None, None)); continue
        if not relationship_id.strip(): _fail("blank-hyperlink-attribute", part.value, "r:id", "")
        if relationship_id in ids: _fail("duplicate-hyperlink-relationship-id", part.value, "r:id", relationship_id)
        ids.add(relationship_id)
        matches = tuple(item for item in relationships if item.source == part and item.id == relationship_id)
        if not matches: _fail("missing-hyperlink-relationship", part.value, "r:id", relationship_id)
        if len(matches) != 1: _fail("ambiguous-hyperlink-relationship", part.value, "r:id", relationship_id)
        relationship = matches[0]
        if relationship.type_uri != _HYPERLINK_TYPE: _fail("non-hyperlink-relationship", part.value, "r:id", relationship_id)
        if relationship.target_mode == "Internal" and relationship.resolved_target is None:
            _fail("dangling-hyperlink-relationship", part.value, "r:id", relationship_id)
        records.append(WorksheetHyperlink(ref, relationship_id, None, element.attrib.get("display"), element.attrib.get("tooltip"), relationship.target_mode, relationship.target, relationship.resolved_target))
    return tuple(records)


def read_worksheet_cell_semantics(package_path: os.PathLike[str] | str) -> WorkbookCellSemantics:
    """Read strict cell/formula/hyperlink metadata for topology worksheets."""
    path = _coerce_package_path(package_path)
    try:
        topology = read_workbook_topology(path)
        graph = build_opc_package_graph(path)
    except (OPCWorkbookTopologyError, OPCPackageGraphError) as error:
        _fail(error.code, error.subject, error.field, error.detail)
    worksheets = []
    for worksheet in topology.worksheets:
        root = _parse_xml(_read_part(path, worksheet.worksheet_part), worksheet.worksheet_part)
        worksheets.append(WorksheetCells(worksheet, _cells(root, worksheet.worksheet_part), _hyperlinks(root, worksheet.worksheet_part, graph.relationships)))
    return WorkbookCellSemantics(tuple(worksheets))
