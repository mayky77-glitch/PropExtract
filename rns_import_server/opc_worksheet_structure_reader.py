"""Strict immutable geometry metadata for accepted SpreadsheetML worksheets."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import OPCWorkbookTopologyError, WorksheetDescriptor, read_workbook_topology
from .opc_worksheet_cell_reader import OPCWorksheetCellReaderError, WorksheetCells, read_worksheet_cell_semantics

_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_WORKSHEET: Final = f"{{{_SML}}}worksheet"
_DIMENSION: Final = f"{{{_SML}}}dimension"
_SHEET_DATA: Final = f"{{{_SML}}}sheetData"
_ROW: Final = f"{{{_SML}}}row"
_AUTO_FILTER: Final = f"{{{_SML}}}autoFilter"
_MERGE_CELLS: Final = f"{{{_SML}}}mergeCells"
_MERGE_CELL: Final = f"{{{_SML}}}mergeCell"
_A1: Final = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})\Z")
_UINT: Final = re.compile(r"[0-9]+\Z")
_DECIMAL: Final = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_BOOL: Final = {"0": False, "1": True, "false": False, "true": True}
_MAX_ROW: Final = 1_048_576
_MAX_COLUMN: Final = 16_384
_MAX_UINT: Final = 4_294_967_295
_XML_ENCODING: Final = re.compile(br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']', re.I)


@dataclass(frozen=True)
class A1Range:
    start: str
    end: str
    min_row: int
    max_row: int
    min_column: int
    max_column: int


@dataclass(frozen=True)
class WorksheetRowProperties:
    row: int
    height: float | None
    style_index: int | None
    custom_height: bool | None
    custom_format: bool | None
    hidden: bool | None
    outline_level: int | None
    collapsed: bool | None


@dataclass(frozen=True)
class WorksheetAutoFilter:
    reference: A1Range


@dataclass(frozen=True)
class WorksheetStructuralSemantics:
    worksheet: WorksheetDescriptor
    dimension: A1Range | None
    rows: tuple[WorksheetRowProperties, ...]
    merges: tuple[A1Range, ...]
    auto_filter: WorksheetAutoFilter | None


@dataclass(frozen=True)
class WorkbookWorksheetStructureSemantics:
    worksheets: tuple[WorksheetStructuralSemantics, ...]


@dataclass
class OPCWorksheetStructureReaderError(ValueError):
    code: str
    subject: str
    field: str
    detail: str
    def __post_init__(self) -> None: ValueError.__init__(self, self.code, self.subject, self.field, self.detail)
    def as_tuple(self) -> tuple[str, str, str, str]: return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetStructureReaderError(code, subject, field, detail)


def _coerce_path(value: os.PathLike[str] | str) -> str:
    subject = f"{type(value).__module__}.{type(value).__qualname__}"
    try: path = os.fspath(value)
    except TypeError as error: _fail("invalid-package-path", subject, "path", type(error).__name__)
    except (ValueError, OSError) as error: _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str): _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path: _fail("unreadable-package", path, "path", "embedded-nul")
    return path


def _nonwhite(value: str | None) -> bool: return bool(value and not value.isspace())
def _mixed(element: ET.Element, part: str, field: str) -> None:
    if _nonwhite(element.text): _fail("invalid-worksheet-content", part, field, "text")
    for child in element:
        if _nonwhite(child.tail): _fail("invalid-worksheet-content", part, field, "tail")


def _uint(value: str | None, part: str, field: str, code: str) -> int:
    text = value or ""
    if _UINT.fullmatch(text) is None or len(text) > 10 or int(text) > _MAX_UINT: _fail(code, part, field, text)
    return int(text)


def _bool(value: str, part: str, field: str) -> bool:
    if value not in _BOOL: _fail("invalid-row-property", part, field, value)
    return _BOOL[value]


def _range(value: str | None, part: str, field: str) -> A1Range:
    text = value or ""
    pieces = text.split(":")
    if len(pieces) not in {1, 2} or not text: _fail("invalid-a1-range", part, field, text)
    points: list[tuple[int, int, str]] = []
    for piece in pieces:
        match = _A1.fullmatch(piece)
        if match is None: _fail("invalid-a1-range", part, field, text)
        column = 0
        for char in match.group(1).upper(): column = column * 26 + ord(char) - ord("A") + 1
        row = int(match.group(2))
        if column > _MAX_COLUMN or row > _MAX_ROW: _fail("invalid-a1-range", part, field, text)
        points.append((row, column, f"{match.group(1).upper()}{row}"))
    first, last = points[0], points[-1]
    if first[0] > last[0] or first[1] > last[1]: _fail("invalid-a1-range", part, field, text)
    return A1Range(first[2], last[2], min(first[0], last[0]), max(first[0], last[0]), min(first[1], last[1]), max(first[1], last[1]))


def _xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    if _XML_ENCODING.match(candidate) is not None:
        try: ET.fromstring(payload)
        except (LookupError, ValueError): _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    try: root = ET.fromstring(payload)
    except LookupError: _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except (ET.ParseError, UnicodeError, ValueError): _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    if root.tag != _WORKSHEET: _fail("invalid-worksheet-root", part.value, "root", str(root.tag))
    _mixed(root, part.value, "worksheet")
    return root


def _member(path: str, part: CanonicalPartURI) -> bytes:
    try:
        with ZipFile(path) as archive:
            matches = []
            for info in archive.infolist():
                try: canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError: _fail("unreadable-worksheet-part", part.value, "member", "invalid-member-name")
                if canonical == part: matches.append(info)
            if not matches: _fail("missing-worksheet-member", part.value, "member", part.value)
            if len(matches) != 1: _fail("ambiguous-worksheet-member", part.value, "member", part.value)
            if matches[0].filename != part.value: _fail("noncanonical-worksheet-member", part.value, "member", matches[0].filename)
            return archive.read(matches[0])
    except OPCWorksheetStructureReaderError: raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error:
        _fail("unreadable-worksheet-part", part.value, "xml", type(error).__name__)
    raise AssertionError("unreachable")


def _row(element: ET.Element, part: str, previous: int) -> WorksheetRowProperties:
    allowed = {"r", "ht", "s", "customHeight", "customFormat", "hidden", "outlineLevel", "collapsed", "spans"}
    unknown = sorted(set(element.attrib) - allowed)
    if unknown: _fail("unknown-row-attribute", part, "attribute", unknown[0])
    row = _uint(element.attrib.get("r"), part, "r", "invalid-row")
    if row == 0 or row > _MAX_ROW or row <= previous: _fail("out-of-order-row" if row <= previous else "invalid-row", part, "r", element.attrib.get("r", ""))
    height = None
    if "ht" in element.attrib:
        text = element.attrib["ht"]
        if _DECIMAL.fullmatch(text) is None: _fail("invalid-row-property", part, "ht", text)
        height = float(text)
    style = _uint(element.attrib["s"], part, "s", "invalid-row-property") if "s" in element.attrib else None
    outline = _uint(element.attrib["outlineLevel"], part, "outlineLevel", "invalid-row-property") if "outlineLevel" in element.attrib else None
    if outline is not None and outline > 7: _fail("invalid-row-property", part, "outlineLevel", element.attrib["outlineLevel"])
    return WorksheetRowProperties(row, height, style, _bool(element.attrib["customHeight"], part, "customHeight") if "customHeight" in element.attrib else None, _bool(element.attrib["customFormat"], part, "customFormat") if "customFormat" in element.attrib else None, _bool(element.attrib["hidden"], part, "hidden") if "hidden" in element.attrib else None, outline, _bool(element.attrib["collapsed"], part, "collapsed") if "collapsed" in element.attrib else None)


def _structure(root: ET.Element, part: CanonicalPartURI, cells: WorksheetCells) -> tuple[A1Range | None, tuple[WorksheetRowProperties, ...], tuple[A1Range, ...], WorksheetAutoFilter | None]:
    owned = {_DIMENSION: "dimension", _SHEET_DATA: "sheetData", _AUTO_FILTER: "autoFilter", _MERGE_CELLS: "mergeCells"}
    elements = [child for child in root if child.tag in owned]
    order = [_DIMENSION, _SHEET_DATA, _AUTO_FILTER, _MERGE_CELLS]
    positions = [order.index(element.tag) for element in elements]
    if positions != sorted(positions): _fail("invalid-worksheet-child-order", part.value, "tag", str([element.tag for element in elements]))
    for tag in owned:
        if sum(child.tag == tag for child in root) > 1: _fail("duplicate-worksheet-container", part.value, owned[tag], "")
    dimension_element = next((e for e in elements if e.tag == _DIMENSION), None)
    dimension = None
    if dimension_element is not None:
        if set(dimension_element.attrib) - {"ref"}: _fail("unknown-dimension-attribute", part.value, "attribute", sorted(set(dimension_element.attrib) - {"ref"})[0])
        if len(dimension_element) or _nonwhite(dimension_element.text): _fail("invalid-worksheet-content", part.value, "dimension", "nested")
        dimension = _range(dimension_element.attrib.get("ref"), part.value, "ref")
    sheet_data = next((e for e in elements if e.tag == _SHEET_DATA), None)
    if sheet_data is None: _fail("missing-sheet-data", part.value, "sheetData", "")
    if sheet_data.attrib: _fail("unknown-sheet-data-attribute", part.value, "attribute", sorted(sheet_data.attrib)[0])
    _mixed(sheet_data, part.value, "sheetData")
    rows: list[WorksheetRowProperties] = []; previous = 0
    for item in sheet_data:
        if item.tag != _ROW: _fail("invalid-sheet-data-child", part.value, "tag", str(item.tag))
        _mixed(item, part.value, "row")
        rows.append(_row(item, part.value, previous)); previous = rows[-1].row
    projected = {cell.row for cell in cells.cells}
    if not projected.issubset({row.row for row in rows}): _fail("cell-row-structure-mismatch", part.value, "row", "missing")
    merge_container = next((e for e in elements if e.tag == _MERGE_CELLS), None)
    merges: list[A1Range] = []
    if merge_container is not None:
        if set(merge_container.attrib) - {"count"}: _fail("unknown-merge-cells-attribute", part.value, "attribute", sorted(set(merge_container.attrib) - {"count"})[0])
        _mixed(merge_container, part.value, "mergeCells")
        seen: set[tuple[str, str]] = set()
        for item in merge_container:
            if item.tag != _MERGE_CELL: _fail("invalid-merge-cells-child", part.value, "tag", str(item.tag))
            if set(item.attrib) - {"ref"}: _fail("unknown-merge-cell-attribute", part.value, "attribute", sorted(set(item.attrib) - {"ref"})[0])
            if len(item) or _nonwhite(item.text): _fail("invalid-worksheet-content", part.value, "mergeCell", "nested")
            record = _range(item.attrib.get("ref"), part.value, "ref")
            key = (record.start, record.end)
            if key in seen: _fail("duplicate-merge-range", part.value, "ref", f"{record.start}:{record.end}" if record.start != record.end else record.start)
            seen.add(key); merges.append(record)
        if "count" in merge_container.attrib and _uint(merge_container.attrib["count"], part.value, "count", "invalid-merge-count") != len(merges): _fail("merge-count-mismatch", part.value, "count", merge_container.attrib["count"])
    filter_element = next((e for e in elements if e.tag == _AUTO_FILTER), None)
    auto = None
    if filter_element is not None:
        if set(filter_element.attrib) - {"ref"}: _fail("unknown-auto-filter-attribute", part.value, "attribute", sorted(set(filter_element.attrib) - {"ref"})[0])
        if len(filter_element) or _nonwhite(filter_element.text): _fail("invalid-auto-filter-content", part.value, "autoFilter", "nested")
        auto = WorksheetAutoFilter(_range(filter_element.attrib.get("ref"), part.value, "ref"))
    return dimension, tuple(rows), tuple(merges), auto


def read_worksheet_structure_semantics(package_path: os.PathLike[str] | str) -> WorkbookWorksheetStructureSemantics:
    """Read immutable native worksheet geometry for insertion preflight."""
    path = _coerce_path(package_path)
    try:
        topology = read_workbook_topology(path)
        projection = read_worksheet_cell_semantics(path)
    except (OPCWorkbookTopologyError, OPCWorksheetCellReaderError) as error:
        _fail(error.code, error.subject, error.field, error.detail)
    by_part = {item.worksheet.worksheet_part: item for item in projection.worksheets}
    records = []
    for worksheet in topology.worksheets:
        cells = by_part.get(worksheet.worksheet_part)
        if cells is None: _fail("worksheet-projection-mismatch", worksheet.worksheet_part.value, "worksheet", "missing")
        root = _xml(_member(path, worksheet.worksheet_part), worksheet.worksheet_part)
        dimension, rows, merges, auto = _structure(root, worksheet.worksheet_part, cells)
        records.append(WorksheetStructuralSemantics(worksheet, dimension, rows, merges, auto))
    return WorkbookWorksheetStructureSemantics(tuple(records))
