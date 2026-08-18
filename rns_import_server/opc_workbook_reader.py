"""Namespace-aware, read-only semantic model for XLSX OPC workbooks.

This module intentionally reads the package directly.  It is not a workbook
writer and package digests are evidence, never an authority for semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile


NS = {
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL_OFFICE_DOCUMENT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
REL_WORKSHEET = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
REL_SHARED_STRINGS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings"
REL_STYLES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
REL_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"


@dataclass(frozen=True)
class Finding:
    code: str
    part: str
    detail: str


class OPCWorkbookError(ValueError):
    """A package invariant failed before a semantic model could be trusted."""

    def __init__(self, code: str, part: str, detail: str) -> None:
        self.finding = Finding(code, part, detail)
        super().__init__(f"{code}: {part}: {detail}")


@dataclass(frozen=True)
class Relationship:
    id: str
    type: str
    target: str
    target_mode: str
    resolved_target: str | None


@dataclass(frozen=True)
class ContentType:
    part_name: str | None
    extension: str | None
    content_type: str


@dataclass(frozen=True)
class Formula:
    text: str
    kind: str | None
    shared_index: int | None
    ref: str | None


@dataclass(frozen=True)
class Cell:
    coordinate: str
    cell_type: str | None
    raw_value: str | None
    value: str | None
    shared_string_index: int | None
    inline_string: str | None
    error: str | None
    formula: Formula | None
    cached_value: str | None
    style_index: int | None
    style_fingerprint: str | None


@dataclass(frozen=True)
class Row:
    index: int
    height: float | None
    hidden: bool
    outline_level: int
    style_index: int | None
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class Column:
    minimum: int
    maximum: int
    width: float | None
    hidden: bool
    outline_level: int
    style_index: int | None


@dataclass(frozen=True)
class Font:
    name: str | None
    size: float | None
    bold: bool
    italic: bool
    color: str | None


@dataclass(frozen=True)
class Fill:
    pattern_type: str | None
    foreground_color: str | None
    background_color: str | None


@dataclass(frozen=True)
class Border:
    left: str | None
    right: str | None
    top: str | None
    bottom: str | None


@dataclass(frozen=True)
class CellStyle:
    number_format: str | None
    font: Font | None
    fill: Fill | None
    border: Border | None
    alignment: tuple[tuple[str, str], ...]
    protection: tuple[tuple[str, str], ...]
    fingerprint: str


@dataclass(frozen=True)
class Hyperlink:
    reference: str
    location: str | None
    display: str | None
    tooltip: str | None
    relationship: Relationship | None


@dataclass(frozen=True)
class DefinedName:
    name: str
    text: str
    local_sheet_id: int | None
    hidden: bool


@dataclass(frozen=True)
class Worksheet:
    name: str
    sheet_id: int
    state: str
    part: str
    dimension: str | None
    rows: tuple[Row, ...]
    columns: tuple[Column, ...]
    hyperlinks: tuple[Hyperlink, ...]
    merges: tuple[str, ...]
    auto_filter: str | None
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class WorkbookModel:
    contract_version: str
    content_types: tuple[ContentType, ...]
    package_relationships: tuple[Relationship, ...]
    sheets: tuple[Worksheet, ...]
    defined_names: tuple[DefinedName, ...]
    styles: tuple[CellStyle, ...]
    relationships: tuple[Relationship, ...]
    part_digests: tuple[tuple[str, str], ...]
    findings: tuple[Finding, ...]


def _tag(name: str) -> str:
    return f"{{{NS['x']}}}{name}"


def _bool(value: str | None) -> bool:
    return value in {"1", "true", "True"}


def _integer(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError as error:
        raise OPCWorkbookError("invalid-integer", "", value or "") from error


def _float(value: str | None) -> float | None:
    return float(value) if value is not None else None


def _text(element: ET.Element | None) -> str | None:
    return None if element is None else "".join(element.itertext())


def _normal_part(name: str, *, source: str = "") -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise OPCWorkbookError("invalid-part-path", source or name, name)
    pieces: list[str] = []
    for piece in name.split("/"):
        if piece in {"", "."}:
            continue
        if piece == "..":
            if not pieces:
                raise OPCWorkbookError("part-traversal", source or name, name)
            pieces.pop()
        else:
            pieces.append(piece)
    normalized = "/".join(pieces)
    if normalized in {".", ""}:
        raise OPCWorkbookError("part-traversal", source or name, name)
    return normalized


def _resolve_target(source_part: str, target: str) -> str:
    if not target or target.startswith("/") or "\\" in target:
        raise OPCWorkbookError("invalid-relationship-target", source_part, target)
    if ".." in target.split("/"):
        raise OPCWorkbookError("part-traversal", source_part, target)
    parent = PurePosixPath(source_part).parent
    candidate = str(parent.joinpath(target))
    return _normal_part(candidate, source=source_part)


def _relationships(raw: bytes, source_part: str, parts: set[str], *, root: bool = False) -> tuple[Relationship, ...]:
    try:
        document = ET.fromstring(raw)
    except ET.ParseError as error:
        raise OPCWorkbookError("malformed-relationships", source_part, str(error)) from error
    result: list[Relationship] = []
    seen: set[str] = set()
    for item in document.findall("pr:Relationship", NS):
        relation_id = item.get("Id")
        relation_type = item.get("Type")
        target = item.get("Target")
        mode = item.get("TargetMode", "Internal")
        if not relation_id or not relation_type or target is None or relation_id in seen or mode not in {"Internal", "External"}:
            raise OPCWorkbookError("malformed-relationship", source_part, ET.tostring(item, encoding="unicode"))
        seen.add(relation_id)
        if root and ".." in target.split("/"):
            raise OPCWorkbookError("part-traversal", source_part, target)
        resolved = None if mode == "External" else (_normal_part(target, source=source_part) if root else _resolve_target(source_part, target))
        if resolved is not None and resolved not in parts:
            raise OPCWorkbookError("missing-relationship-target", source_part, resolved)
        result.append(Relationship(relation_id, relation_type, target, mode, resolved))
    return tuple(result)


def _color(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    for key in ("rgb", "theme", "indexed", "auto"):
        if key in element.attrib:
            return f"{key}:{element.attrib[key]}"
    return None


def _side(element: ET.Element | None) -> str | None:
    return None if element is None else element.get("style")


def _parse_styles(raw: bytes | None) -> tuple[CellStyle, ...]:
    if raw is None:
        return ()
    root = ET.fromstring(raw)
    custom_formats = {item.get("numFmtId"): item.get("formatCode") for item in root.findall("x:numFmts/x:numFmt", NS)}
    fonts = tuple(Font(item.find("x:name", NS).get("val") if item.find("x:name", NS) is not None else None, _float(item.find("x:sz", NS).get("val") if item.find("x:sz", NS) is not None else None), item.find("x:b", NS) is not None, item.find("x:i", NS) is not None, _color(item.find("x:color", NS))) for item in root.findall("x:fonts/x:font", NS))
    fills = tuple(Fill(item.find("x:patternFill", NS).get("patternType") if item.find("x:patternFill", NS) is not None else None, _color(item.find("x:patternFill/x:fgColor", NS)), _color(item.find("x:patternFill/x:bgColor", NS))) for item in root.findall("x:fills/x:fill", NS))
    borders = tuple(Border(_side(item.find("x:left", NS)), _side(item.find("x:right", NS)), _side(item.find("x:top", NS)), _side(item.find("x:bottom", NS))) for item in root.findall("x:borders/x:border", NS))
    builtins = {0: "General", 14: "mm-dd-yy", 22: "m/d/yy h:mm"}
    styles: list[CellStyle] = []
    for xf in root.findall("x:cellXfs/x:xf", NS):
        num_id = _integer(xf.get("numFmtId"))
        font_id, fill_id, border_id = (_integer(xf.get(key)) for key in ("fontId", "fillId", "borderId"))
        alignment_node = xf.find("x:alignment", NS)
        protection_node = xf.find("x:protection", NS)
        alignment = tuple(sorted(alignment_node.attrib.items())) if alignment_node is not None else ()
        protection = tuple(sorted(protection_node.attrib.items())) if protection_node is not None else ()
        number_format = custom_formats.get(str(num_id), builtins.get(num_id, f"builtin:{num_id}"))
        value = (number_format, fonts[font_id] if font_id < len(fonts) else None, fills[fill_id] if fill_id < len(fills) else None, borders[border_id] if border_id < len(borders) else None, alignment, protection)
        styles.append(CellStyle(*value, fingerprint=sha256(repr(value).encode()).hexdigest()))
    return tuple(styles)


def _content_types(raw: bytes) -> tuple[ContentType, ...]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise OPCWorkbookError("malformed-content-types", "[Content_Types].xml", str(error)) from error
    if root.tag != f"{{{NS['ct']}}}Types":
        raise OPCWorkbookError("invalid-content-types", "[Content_Types].xml", root.tag)
    result: list[ContentType] = []
    for item in root:
        content_type = item.get("ContentType")
        if item.tag == f"{{{NS['ct']}}}Default":
            extension = item.get("Extension")
            if not extension or not content_type:
                raise OPCWorkbookError("invalid-content-type", "[Content_Types].xml", ET.tostring(item, encoding="unicode"))
            result.append(ContentType(None, extension, content_type))
        elif item.tag == f"{{{NS['ct']}}}Override":
            name = item.get("PartName")
            if not name or not name.startswith("/") or not content_type:
                raise OPCWorkbookError("invalid-content-type", "[Content_Types].xml", ET.tostring(item, encoding="unicode"))
            result.append(ContentType(_normal_part(name[1:], source="[Content_Types].xml"), None, content_type))
    return tuple(result)


def _shared_strings(raw: bytes | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    root = ET.fromstring(raw)
    return tuple(_text(item) or "" for item in root.findall("x:si", NS))


def _unsupported(root: ET.Element, part: str) -> tuple[Finding, ...]:
    names = {"conditionalFormatting", "dataValidations", "tableParts", "drawing", "legacyDrawing", "extLst", "sheetProtection"}
    return tuple(Finding("unsupported-feature", part, name) for name in names if root.find(f"x:{name}", NS) is not None)


def _cell(item: ET.Element, strings: tuple[str, ...], styles: tuple[CellStyle, ...], part: str) -> Cell:
    coordinate = item.get("r")
    if not coordinate:
        raise OPCWorkbookError("missing-cell-coordinate", part, ET.tostring(item, encoding="unicode"))
    cell_type = item.get("t")
    raw = _text(item.find("x:v", NS))
    inline = _text(item.find("x:is", NS))
    formula_node = item.find("x:f", NS)
    formula = None if formula_node is None else Formula(_text(formula_node) or "", formula_node.get("t"), _integer(formula_node.get("si")) if formula_node.get("si") else None, formula_node.get("ref"))
    shared_index = None
    value = raw
    error = raw if cell_type == "e" else None
    if cell_type == "s":
        if raw is None:
            raise OPCWorkbookError("missing-shared-string-index", part, coordinate)
        shared_index = _integer(raw)
        if not 0 <= shared_index < len(strings):
            raise OPCWorkbookError("shared-string-index-out-of-range", part, raw)
        value = strings[shared_index]
    elif cell_type == "inlineStr":
        value = inline
    style_index = _integer(item.get("s")) if item.get("s") else None
    if style_index is not None and style_index >= len(styles):
        raise OPCWorkbookError("style-index-out-of-range", part, str(style_index))
    return Cell(coordinate, cell_type, raw, value, shared_index, inline, error, formula, raw if formula else None, style_index, styles[style_index].fingerprint if style_index is not None else None)


def _worksheet(raw: bytes, name: str, sheet_id: int, state: str, part: str, strings: tuple[str, ...], styles: tuple[CellStyle, ...], relationships: tuple[Relationship, ...]) -> Worksheet:
    root = ET.fromstring(raw)
    rows = tuple(Row(_integer(item.get("r")), _float(item.get("ht")), _bool(item.get("hidden")), _integer(item.get("outlineLevel")), _integer(item.get("s")) if item.get("s") else None, tuple(_cell(cell, strings, styles, part) for cell in item.findall("x:c", NS))) for item in root.findall("x:sheetData/x:row", NS))
    columns = tuple(Column(_integer(item.get("min")), _integer(item.get("max")), _float(item.get("width")), _bool(item.get("hidden")), _integer(item.get("outlineLevel")), _integer(item.get("style")) if item.get("style") else None) for item in root.findall("x:cols/x:col", NS))
    rel_by_id = {relation.id: relation for relation in relationships}
    links: list[Hyperlink] = []
    for link in root.findall("x:hyperlinks/x:hyperlink", NS):
        relation_id = link.get(f"{{{NS['r']}}}id")
        relationship = rel_by_id.get(relation_id) if relation_id else None
        if relation_id and relationship is None:
            raise OPCWorkbookError("missing-hyperlink-relationship", part, relation_id)
        links.append(Hyperlink(link.get("ref", ""), link.get("location"), link.get("display"), link.get("tooltip"), relationship))
    dimension_node = root.find("x:dimension", NS)
    filter_node = root.find("x:autoFilter", NS)
    return Worksheet(name, sheet_id, state, part, dimension_node.get("ref") if dimension_node is not None else None, rows, columns, tuple(links), tuple(item.get("ref", "") for item in root.findall("x:mergeCells/x:mergeCell", NS)), filter_node.get("ref") if filter_node is not None else None, _unsupported(root, part))


def read_opc_workbook(path: str) -> WorkbookModel:
    """Read workbook at *path*, rejecting unsafe/malformed OPC relationships."""
    with ZipFile(path) as archive:
        members = archive.infolist()
        parts: dict[str, bytes] = {}
        for member in members:
            normalized = _normal_part(member.filename)
            if normalized in parts:
                raise OPCWorkbookError("duplicate-normalized-part", normalized, member.filename)
            parts[normalized] = archive.read(member)
    if "[Content_Types].xml" not in parts or "_rels/.rels" not in parts:
        raise OPCWorkbookError("missing-opc-root", "", "[Content_Types].xml or _rels/.rels")
    content_types = _content_types(parts["[Content_Types].xml"])
    package_relationships = _relationships(parts["_rels/.rels"], "_rels/.rels", set(parts), root=True)
    office = next((item for item in package_relationships if item.type == REL_OFFICE_DOCUMENT), None)
    if office is None or office.resolved_target is None:
        raise OPCWorkbookError("missing-office-document", "_rels/.rels", "officeDocument")
    workbook_part = office.resolved_target
    workbook_rels_part = str(PurePosixPath(workbook_part).parent / "_rels" / f"{PurePosixPath(workbook_part).name}.rels")
    if workbook_rels_part not in parts:
        raise OPCWorkbookError("missing-workbook-relationships", workbook_part, workbook_rels_part)
    workbook_relationships = _relationships(parts[workbook_rels_part], workbook_part, set(parts))
    relation_by_id = {item.id: item for item in workbook_relationships}
    strings_rel = next((item for item in workbook_relationships if item.type == REL_SHARED_STRINGS), None)
    styles_rel = next((item for item in workbook_relationships if item.type == REL_STYLES), None)
    strings = _shared_strings(parts[strings_rel.resolved_target]) if strings_rel and strings_rel.resolved_target else ()
    styles = _parse_styles(parts[styles_rel.resolved_target]) if styles_rel and styles_rel.resolved_target else ()
    root = ET.fromstring(parts[workbook_part])
    sheets: list[Worksheet] = []
    for item in root.findall("x:sheets/x:sheet", NS):
        relation_id = item.get(f"{{{NS['r']}}}id")
        relation = relation_by_id.get(relation_id)
        if relation is None or relation.type != REL_WORKSHEET or relation.resolved_target is None:
            raise OPCWorkbookError("invalid-sheet-relationship", workbook_part, relation_id or "")
        worksheet_part = relation.resolved_target
        worksheet_rels_part = str(PurePosixPath(worksheet_part).parent / "_rels" / f"{PurePosixPath(worksheet_part).name}.rels")
        worksheet_relationships = _relationships(parts[worksheet_rels_part], worksheet_part, set(parts)) if worksheet_rels_part in parts else ()
        sheets.append(_worksheet(parts[worksheet_part], item.get("name", ""), _integer(item.get("sheetId")), item.get("state", "visible"), worksheet_part, strings, styles, worksheet_relationships))
    names = tuple(DefinedName(item.get("name", ""), _text(item) or "", _integer(item.get("localSheetId")) if item.get("localSheetId") else None, _bool(item.get("hidden"))) for item in root.findall("x:definedNames/x:definedName", NS))
    findings = tuple(finding for sheet in sheets for finding in sheet.findings)
    return WorkbookModel("opc-workbook-model-v1", content_types, package_relationships, tuple(sheets), names, styles, workbook_relationships, tuple(sorted((name, sha256(raw).hexdigest()) for name, raw in parts.items())), findings)


read_workbook = read_opc_workbook
