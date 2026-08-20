"""Strict, immutable native SpreadsheetML style semantics reader."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import re
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile

from .opc_package_graph import OPCPackageGraphError, build_opc_package_graph
from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorkbookTopology, read_workbook_topology
from .opc_worksheet_cell_reader import WorkbookCellSemantics, read_worksheet_cell_semantics


_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CT: Final = "http://schemas.openxmlformats.org/package/2006/content-types"
_XR: Final = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
_STYLES_REL: Final = f"{_REL}/styles"
_STYLES_CONTENT_TYPE: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"
_STYLES: Final = f"{{{_SML}}}styleSheet"
_TYPES: Final = f"{{{_CT}}}Types"
_OVERRIDE: Final = f"{{{_CT}}}Override"
_XML_ENCODING: Final = re.compile(br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']', re.I)
_UINT: Final = re.compile(r"[0-9]+\Z")
_INT: Final = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_BOOL: Final = {"0": False, "1": True, "false": False, "true": True}
_MAX_UINT: Final = 4_294_967_295
_ARGB: Final = re.compile(r"[0-9A-Fa-f]{8}\Z")
_UNDERLINE: Final = frozenset({"single", "double", "singleAccounting", "doubleAccounting", "none"})
_VERT_ALIGN: Final = frozenset({"baseline", "superscript", "subscript"})
_SCHEME: Final = frozenset({"major", "minor", "none"})
_PATTERNS: Final = frozenset({"none", "solid", "mediumGray", "darkGray", "lightGray", "darkHorizontal", "darkVertical", "darkDown", "darkUp", "darkGrid", "darkTrellis", "lightHorizontal", "lightVertical", "lightDown", "lightUp", "lightGrid", "lightTrellis", "gray125", "gray0625"})
_BORDER_STYLES: Final = frozenset({"none", "thin", "medium", "dashed", "dotted", "thick", "double", "hair", "mediumDashed", "dashDot", "mediumDashDot", "dashDotDot", "mediumDashDotDot", "slantDashDot"})
_HORIZONTAL: Final = frozenset({"general", "left", "center", "right", "fill", "justify", "centerContinuous", "distributed"})
_VERTICAL: Final = frozenset({"top", "center", "bottom", "justify", "distributed"})


@dataclass(frozen=True)
class StyleColor:
    rgb: str | None; indexed: int | None; theme: int | None; tint: float | None; auto: bool | None

@dataclass(frozen=True)
class FontStyle:
    name: str | None; size: float | None; family: int | None; charset: int | None; scheme: str | None; color: StyleColor | None
    bold: bool; italic: bool; underline: str | None; strike: bool; outline: bool; shadow: bool; condense: bool; extend: bool; vert_align: str | None

@dataclass(frozen=True)
class FillStyle:
    kind: str; pattern_type: str | None; foreground: StyleColor | None; background: StyleColor | None
    gradient_type: str | None; degree: str | None; left: str | None; right: str | None; top: str | None; bottom: str | None; stops: tuple[tuple[float, StyleColor], ...]

@dataclass(frozen=True)
class BorderSide:
    style: str | None; color: StyleColor | None

@dataclass(frozen=True)
class BorderStyle:
    left: BorderSide; right: BorderSide; top: BorderSide; bottom: BorderSide; diagonal: BorderSide
    diagonal_up: bool | None; diagonal_down: bool | None; outline: bool | None; vertical: BorderSide | None; horizontal: BorderSide | None

@dataclass(frozen=True)
class NumberFormat:
    num_fmt_id: int; format_code: str

@dataclass(frozen=True)
class CellAlignment:
    horizontal: str | None; vertical: str | None; text_rotation: int | None; wrap_text: bool | None; shrink_to_fit: bool | None; indent: int | None; relative_indent: int | None; justify_last_line: bool | None; reading_order: int | None

@dataclass(frozen=True)
class CellProtection:
    locked: bool | None; hidden: bool | None

@dataclass(frozen=True)
class CellFormat:
    num_fmt_id: int; font_id: int; fill_id: int; border_id: int; xf_id: int | None
    apply_number_format: bool | None; apply_font: bool | None; apply_fill: bool | None; apply_border: bool | None; apply_alignment: bool | None; apply_protection: bool | None; quote_prefix: bool | None; pivot_button: bool | None
    alignment: CellAlignment | None; protection: CellProtection | None

@dataclass(frozen=True)
class StyleTable:
    number_formats: tuple[NumberFormat, ...]; fonts: tuple[FontStyle, ...]; fills: tuple[FillStyle, ...]; borders: tuple[BorderStyle, ...]; cell_style_xfs: tuple[CellFormat, ...]; cell_xfs: tuple[CellFormat, ...]

@dataclass(frozen=True)
class CellStyleUse:
    coordinate: str; row: int; column: int; style_index: int

@dataclass(frozen=True)
class WorksheetStyleUsage:
    worksheet_name: str; worksheet_part: CanonicalPartURI; cells: tuple[CellStyleUse, ...]

@dataclass(frozen=True)
class WorkbookStyleSemantics:
    style_part: CanonicalPartURI; style_table: StyleTable; worksheets: tuple[WorksheetStyleUsage, ...]

@dataclass
class OPCStyleSemanticReaderError(ValueError):
    code: str; subject: str; field: str; detail: str
    def __post_init__(self) -> None: ValueError.__init__(self, self.code, self.subject, self.field, self.detail)
    def as_tuple(self) -> tuple[str, str, str, str]: return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None: raise OPCStyleSemanticReaderError(code, subject, field, detail)

def _coerce_path(value: os.PathLike[str] | str) -> str:
    subject = f"{type(value).__module__}.{type(value).__qualname__}"
    try: path = os.fspath(value)
    except TypeError as error: _fail("invalid-package-path", subject, "path", type(error).__name__)
    except (ValueError, OSError) as error: _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str): _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path: _fail("unreadable-package", path, "path", "embedded-nul")
    return path

def _uint(value: str | None, subject: str, field: str, code: str = "invalid-style-index") -> int:
    text = value or ""
    if _UINT.fullmatch(text) is None or len(text) > 10 or int(text) > _MAX_UINT: _fail(code, subject, field, text)
    return int(text)

def _bool(value: str, subject: str, field: str) -> bool:
    if value not in _BOOL: _fail("invalid-styles-content", subject, field, value)
    return _BOOL[value]

def _int(value: str, subject: str, field: str) -> int:
    if _INT.fullmatch(value) is None or len(value) > 11: _fail("invalid-styles-content", subject, field, value)
    number = int(value)
    if not -2_147_483_648 <= number <= 2_147_483_647: _fail("invalid-styles-content", subject, field, value)
    return number

def _finite_float(value: str, subject: str, field: str) -> float:
    try: number = float(value)
    except ValueError: _fail("invalid-styles-content", subject, field, value)
    if not math.isfinite(number): _fail("invalid-styles-content", subject, field, value)
    return number

def _nonwhite(value: str | None) -> bool: return bool(value and not value.isspace())
def _mixed(element: ET.Element, part: str, field: str) -> None:
    if _nonwhite(element.text): _fail("invalid-styles-content", part, field, "text")
    for child in element:
        if _nonwhite(child.tail): _fail("invalid-styles-content", part, field, "tail")

def _read_member(path: str, part: CanonicalPartURI, *, raw_exact: bool) -> bytes:
    try:
        with ZipFile(path) as zf:
            matches = []
            for info in zf.infolist():
                try: canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError: _fail("unreadable-styles-part", part.value, "member", "invalid-member-name")
                if canonical == part:
                    if raw_exact and info.filename != part.value:
                        _fail("noncanonical-styles-member", part.value, "member", info.filename)
                    matches.append(info)
            if not matches: _fail("missing-styles-member", part.value, "member", part.value)
            if len(matches) != 1: _fail("ambiguous-styles-member", part.value, "member", part.value)
            return zf.read(matches[0])
    except OPCStyleSemanticReaderError: raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error: _fail("unreadable-styles-part", part.value, "member", type(error).__name__)
    raise AssertionError("unreachable")

def _xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    if _XML_ENCODING.match(candidate) is not None:
        try: ET.fromstring(payload)
        except (LookupError, ValueError): _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    try: root = ET.fromstring(payload)
    except LookupError: _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except (ET.ParseError, UnicodeError, ValueError): _fail("malformed-styles-xml", part.value, "xml", "xml")
    if root.tag != _STYLES: _fail("invalid-styles-root", part.value, "root", str(root.tag))
    if root.attrib: _fail("unknown-styles-attribute", part.value, "attribute", sorted(root.attrib)[0])
    _mixed(root, part.value, "styleSheet")
    return root

def _color(element: ET.Element, part: str) -> StyleColor:
    allowed = {"rgb", "indexed", "theme", "tint", "auto"}
    unknown = sorted(set(element.attrib) - allowed)
    if unknown: _fail("unknown-styles-attribute", part, "attribute", unknown[0])
    forms = [name for name in ("rgb", "indexed", "theme", "auto") if name in element.attrib]
    if len(forms) > 1: _fail("invalid-styles-content", part, "color", "multiple-color-values")
    indexed = _uint(element.attrib["indexed"], part, "indexed") if "indexed" in element.attrib else None
    theme = _uint(element.attrib["theme"], part, "theme") if "theme" in element.attrib else None
    auto = _bool(element.attrib["auto"], part, "auto") if "auto" in element.attrib else None
    tint = _finite_float(element.attrib["tint"], part, "tint") if "tint" in element.attrib else None
    if tint is not None and not -1 <= tint <= 1: _fail("invalid-styles-content", part, "tint", element.attrib["tint"])
    if "rgb" in element.attrib and _ARGB.fullmatch(element.attrib["rgb"]) is None:
        _fail("invalid-styles-content", part, "rgb", element.attrib["rgb"])
    if len(element) or _nonwhite(element.text): _fail("invalid-styles-content", part, "color", "nested")
    return StyleColor(element.attrib.get("rgb"), indexed, theme, tint, auto)

def _single_color(parent: ET.Element, tag: str, part: str) -> StyleColor | None:
    items = [child for child in parent if child.tag == f"{{{_SML}}}{tag}"]
    if len(items) > 1: _fail("invalid-styles-content", part, tag, "duplicate")
    return _color(items[0], part) if items else None

def _font(element: ET.Element, part: str) -> FontStyle:
    if element.attrib:
        _fail("unknown-styles-attribute", part, "attribute", sorted(element.attrib)[0])
    _mixed(element, part, "font")
    allowed = {"name", "sz", "family", "charset", "scheme", "color", "b", "i", "u", "strike", "outline", "shadow", "condense", "extend", "vertAlign"}
    values: dict[str, ET.Element] = {}
    for child in element:
        local = child.tag.removeprefix(f"{{{_SML}}}")
        if child.tag == local or local not in allowed: _fail("invalid-styles-content", part, "font", str(child.tag))
        if local in values: _fail("invalid-styles-content", part, local, "duplicate")
        if local != "color" and set(child.attrib) - {"val"}: _fail("unknown-styles-attribute", part, "attribute", sorted(set(child.attrib) - {"val"})[0])
        if local == "color" and set(child.attrib) - {"rgb", "indexed", "theme", "tint", "auto"}: _fail("unknown-styles-attribute", part, "attribute", sorted(set(child.attrib) - {"rgb", "indexed", "theme", "tint", "auto"})[0])
        if len(child) or _nonwhite(child.text): _fail("invalid-styles-content", part, local, "nested")
        values[local] = child
    def val(name: str) -> str | None: return values[name].attrib.get("val") if name in values else None
    def flag(name: str) -> bool:
        raw = val(name)
        return True if raw is None and name in values else (_bool(raw, part, name) if raw is not None else False)
    for name in ("family", "charset"):
        if val(name) is not None: _uint(val(name), part, name)
    underline = "single" if "u" in values and val("u") is None else val("u")
    if underline is not None and underline not in _UNDERLINE: _fail("invalid-styles-content", part, "u", underline)
    if val("vertAlign") is not None and val("vertAlign") not in _VERT_ALIGN: _fail("invalid-styles-content", part, "vertAlign", val("vertAlign"))
    if val("scheme") is not None and val("scheme") not in _SCHEME: _fail("invalid-styles-content", part, "scheme", val("scheme"))
    size = _finite_float(val("sz"), part, "sz") if val("sz") is not None else None
    if size is not None and not 1 <= size <= 409.5: _fail("invalid-styles-content", part, "sz", val("sz"))
    return FontStyle(val("name"), size, _uint(val("family"), part, "family") if val("family") is not None else None, _uint(val("charset"), part, "charset") if val("charset") is not None else None, val("scheme"), _color(values["color"], part) if "color" in values else None, flag("b"), flag("i"), underline, flag("strike"), flag("outline"), flag("shadow"), flag("condense"), flag("extend"), val("vertAlign"))

def _fill(element: ET.Element, part: str) -> FillStyle:
    if element.attrib: _fail("unknown-styles-attribute", part, "attribute", sorted(element.attrib)[0])
    _mixed(element, part, "fill")
    if len(element) != 1: _fail("invalid-styles-content", part, "fill", "structure")
    child = element[0]
    if child.tag == f"{{{_SML}}}patternFill":
        if set(child.attrib) - {"patternType"}: _fail("unknown-styles-attribute", part, "attribute", sorted(set(child.attrib) - {"patternType"})[0])
        _mixed(child, part, "patternFill")
        if child.attrib.get("patternType") not in {None, *_PATTERNS}: _fail("invalid-styles-content", part, "patternType", child.attrib["patternType"])
        allowed = {f"{{{_SML}}}fgColor", f"{{{_SML}}}bgColor"}
        if any(item.tag not in allowed for item in child): _fail("invalid-styles-content", part, "patternFill", str(next(item.tag for item in child if item.tag not in allowed)))
        return FillStyle("pattern", child.attrib.get("patternType"), _single_color(child, "fgColor", part), _single_color(child, "bgColor", part), None, None, None, None, None, None, ())
    if child.tag == f"{{{_SML}}}gradientFill":
        allowed_attr = {"type", "degree", "left", "right", "top", "bottom"}
        if set(child.attrib) - allowed_attr: _fail("unknown-styles-attribute", part, "attribute", sorted(set(child.attrib) - allowed_attr)[0])
        _mixed(child, part, "gradientFill"); stops = []
        if child.attrib.get("type", "linear") not in {"linear", "path"}: _fail("invalid-styles-content", part, "type", child.attrib["type"])
        for stop in child:
            if stop.tag != f"{{{_SML}}}stop" or set(stop.attrib) != {"position"} or len(stop) != 1: _fail("invalid-styles-content", part, "gradientFill", "stop")
            _mixed(stop, part, "stop")
            position = _finite_float(stop.attrib["position"], part, "position")
            if not 0 <= position <= 1: _fail("invalid-styles-content", part, "position", stop.attrib["position"])
            stops.append((position, _color(stop[0], part)))
        return FillStyle("gradient", None, None, None, child.attrib.get("type"), child.attrib.get("degree"), child.attrib.get("left"), child.attrib.get("right"), child.attrib.get("top"), child.attrib.get("bottom"), tuple(stops))
    _fail("invalid-styles-content", part, "fill", str(child.tag))

def _border_side(element: ET.Element, part: str) -> BorderSide:
    if set(element.attrib) - {"style"}: _fail("unknown-styles-attribute", part, "attribute", sorted(set(element.attrib) - {"style"})[0])
    _mixed(element, part, "border-side")
    if element.attrib.get("style") not in {None, *_BORDER_STYLES}: _fail("invalid-styles-content", part, "style", element.attrib["style"])
    if len(element) > 1 or (len(element) == 1 and element[0].tag != f"{{{_SML}}}color"): _fail("invalid-styles-content", part, "border-side", "structure")
    return BorderSide(element.attrib.get("style"), _color(element[0], part) if len(element) == 1 else None)

def _border(element: ET.Element, part: str) -> BorderStyle:
    allowed_attr = {"diagonalUp", "diagonalDown", "outline"}; unknown = sorted(set(element.attrib) - allowed_attr)
    if unknown: _fail("unknown-styles-attribute", part, "attribute", unknown[0])
    _mixed(element, part, "border"); allowed = {"left", "right", "top", "bottom", "diagonal", "vertical", "horizontal"}; values: dict[str, BorderSide] = {}
    for child in element:
        local = child.tag.removeprefix(f"{{{_SML}}}")
        if child.tag == local or local not in allowed or local in values: _fail("invalid-styles-content", part, "border", str(child.tag))
        values[local] = _border_side(child, part)
    empty = BorderSide(None, None)
    return BorderStyle(*(values.get(key, empty) for key in ("left", "right", "top", "bottom", "diagonal")), *(_bool(element.attrib[key], part, key) if key in element.attrib else None for key in ("diagonalUp", "diagonalDown", "outline")), values.get("vertical"), values.get("horizontal"))

def _alignment(element: ET.Element, part: str) -> CellAlignment:
    allowed = {"horizontal", "vertical", "textRotation", "wrapText", "shrinkToFit", "indent", "relativeIndent", "justifyLastLine", "readingOrder"}; unknown = sorted(set(element.attrib) - allowed)
    if unknown: _fail("unknown-styles-attribute", part, "attribute", unknown[0])
    if len(element) or _nonwhite(element.text): _fail("invalid-styles-content", part, "alignment", "nested")
    a = element.attrib
    if a.get("horizontal") not in {None, *_HORIZONTAL}: _fail("invalid-styles-content", part, "horizontal", a["horizontal"])
    if a.get("vertical") not in {None, *_VERTICAL}: _fail("invalid-styles-content", part, "vertical", a["vertical"])
    rotation = _int(a["textRotation"], part, "textRotation") if "textRotation" in a else None
    if rotation is not None and rotation not in {*range(181), 255}: _fail("invalid-styles-content", part, "textRotation", a["textRotation"])
    indent = _uint(a["indent"], part, "indent") if "indent" in a else None
    if indent is not None and indent > 250: _fail("invalid-styles-content", part, "indent", a["indent"])
    relative = _int(a["relativeIndent"], part, "relativeIndent") if "relativeIndent" in a else None
    if relative is not None and not -15 <= relative <= 15: _fail("invalid-styles-content", part, "relativeIndent", a["relativeIndent"])
    reading = _uint(a["readingOrder"], part, "readingOrder") if "readingOrder" in a else None
    if reading is not None and reading > 2: _fail("invalid-styles-content", part, "readingOrder", a["readingOrder"])
    return CellAlignment(a.get("horizontal"), a.get("vertical"), rotation, _bool(a["wrapText"], part, "wrapText") if "wrapText" in a else None, _bool(a["shrinkToFit"], part, "shrinkToFit") if "shrinkToFit" in a else None, indent, relative, _bool(a["justifyLastLine"], part, "justifyLastLine") if "justifyLastLine" in a else None, reading)

def _protection(element: ET.Element, part: str) -> CellProtection:
    if set(element.attrib) - {"locked", "hidden"}: _fail("unknown-styles-attribute", part, "attribute", sorted(set(element.attrib) - {"locked", "hidden"})[0])
    if len(element) or _nonwhite(element.text): _fail("invalid-styles-content", part, "protection", "nested")
    return CellProtection(_bool(element.attrib["locked"], part, "locked") if "locked" in element.attrib else None, _bool(element.attrib["hidden"], part, "hidden") if "hidden" in element.attrib else None)

def _xf(element: ET.Element, part: str, *, style_xfs: tuple[CellFormat, ...] | None, limits: tuple[int, int, int]) -> CellFormat:
    attrs = {"numFmtId", "fontId", "fillId", "borderId", "xfId", "applyNumberFormat", "applyFont", "applyFill", "applyBorder", "applyAlignment", "applyProtection", "quotePrefix", "pivotButton"}
    unknown = sorted(set(element.attrib) - attrs)
    if unknown: _fail("unknown-styles-attribute", part, "attribute", unknown[0])
    required = ("numFmtId", "fontId", "fillId", "borderId")
    if any(key not in element.attrib for key in required): _fail("invalid-styles-content", part, "xf", "missing-component")
    num, font, fill, border = (_uint(element.attrib[key], part, key) for key in required)
    if font >= limits[0] or fill >= limits[1] or border >= limits[2]: _fail("invalid-style-index", part, "xf", "component")
    xf_id = _uint(element.attrib["xfId"], part, "xfId") if "xfId" in element.attrib else None
    if xf_id is not None and (style_xfs is None or xf_id >= len(style_xfs)): _fail("invalid-xf-id", part, "xfId", element.attrib["xfId"])
    _mixed(element, part, "xf"); align = None; protect = None
    for child in element:
        if child.tag == f"{{{_SML}}}alignment" and align is None and protect is None: align = _alignment(child, part)
        elif child.tag == f"{{{_SML}}}protection" and protect is None: protect = _protection(child, part)
        else: _fail("invalid-styles-content", part, "xf", str(child.tag))
    def flag(key: str) -> bool | None: return _bool(element.attrib[key], part, key) if key in element.attrib else None
    return CellFormat(num, font, fill, border, xf_id, *(flag(key) for key in ("applyNumberFormat", "applyFont", "applyFill", "applyBorder", "applyAlignment", "applyProtection", "quotePrefix", "pivotButton")), align, protect)

def _container(root: ET.Element, name: str, part: str) -> ET.Element | None:
    tag = f"{{{_SML}}}{name}"; items = [child for child in root if child.tag == tag]
    if len(items) > 1: _fail("invalid-styles-content", part, name, "duplicate")
    return items[0] if items else None

def _collection(root: ET.Element, name: str, child: str, part: str) -> list[ET.Element]:
    container = _container(root, name, part)
    if container is None: return []
    if set(container.attrib) - {"count"}: _fail("unknown-styles-attribute", part, "attribute", sorted(set(container.attrib) - {"count"})[0])
    _mixed(container, part, name)
    items = list(container)
    if any(item.tag != f"{{{_SML}}}{child}" for item in items): _fail("invalid-styles-content", part, name, "child")
    if "count" in container.attrib and _uint(container.attrib["count"], part, "count", "invalid-style-count") != len(items): _fail("invalid-style-count", part, "count", container.attrib["count"])
    return items

def _table(root: ET.Element, part: CanonicalPartURI) -> StyleTable:
    order = ["numFmts", "fonts", "fills", "borders", "cellStyleXfs", "cellXfs"]
    own = [child.tag.removeprefix(f"{{{_SML}}}") for child in root if child.tag.startswith(f"{{{_SML}}}")]
    if any(name not in order for name in own): _fail("invalid-styles-content", part.value, "styleSheet", "unknown-child")
    if [order.index(name) for name in own] != sorted(order.index(name) for name in own): _fail("invalid-styles-content", part.value, "styleSheet", "child-order")
    num_elems = _collection(root, "numFmts", "numFmt", part.value); formats=[]; ids=set()
    for element in num_elems:
        if set(element.attrib) != {"numFmtId", "formatCode"} or len(element) or _nonwhite(element.text): _fail("invalid-styles-content", part.value, "numFmt", "structure")
        ident = _uint(element.attrib["numFmtId"], part.value, "numFmtId")
        if ident in ids: _fail("duplicate-numFmt-id", part.value, "numFmtId", element.attrib["numFmtId"])
        ids.add(ident); formats.append(NumberFormat(ident, element.attrib["formatCode"]))
    fonts = tuple(_font(item, part.value) for item in _collection(root, "fonts", "font", part.value))
    fills = tuple(_fill(item, part.value) for item in _collection(root, "fills", "fill", part.value))
    borders = tuple(_border(item, part.value) for item in _collection(root, "borders", "border", part.value))
    limits = (len(fonts), len(fills), len(borders))
    base = tuple(_xf(item, part.value, style_xfs=None, limits=limits) for item in _collection(root, "cellStyleXfs", "xf", part.value))
    xfs = tuple(_xf(item, part.value, style_xfs=base, limits=limits) for item in _collection(root, "cellXfs", "xf", part.value))
    return StyleTable(tuple(formats), fonts, fills, borders, base, xfs)

def _styles_relationship(topology: WorkbookTopology, path: str) -> CanonicalPartURI:
    try: graph = build_opc_package_graph(path)
    except OPCPackageGraphError as error: _fail(error.code, error.subject, error.field, error.detail)
    rels = [item for item in graph.relationships if item.source == topology.workbook_part and item.type_uri == _STYLES_REL]
    if not rels:
        candidates = _styles_content_type_parts(path)
        wrong = [
            item
            for item in graph.relationships
            if item.source == topology.workbook_part
            and item.target_mode == "Internal"
            and item.resolved_target in candidates
        ]
        if wrong: _fail("wrong-styles-relationship-type", topology.workbook_part.value, "Type", wrong[0].type_uri)
        _fail("missing-styles-relationship", topology.workbook_part.value, "Type", _STYLES_REL)
    if len(rels) != 1: _fail("ambiguous-styles-relationship", topology.workbook_part.value, "Type", _STYLES_REL)
    relationship = rels[0]
    if relationship.target_mode != "Internal": _fail("external-styles-relationship", topology.workbook_part.value, "TargetMode", relationship.target_mode)
    if relationship.resolved_target is None: _fail("dangling-styles-relationship", topology.workbook_part.value, "Target", relationship.target)
    return relationship.resolved_target

def _styles_content_type_parts(path: str) -> frozenset[CanonicalPartURI]:
    try:
        with ZipFile(path) as zf: payload = zf.read("[Content_Types].xml")
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error:
        _fail("unreadable-styles-content-type", "workbook", "content-type", type(error).__name__)
    try: root = ET.fromstring(payload)
    except (ET.ParseError, LookupError, UnicodeError, ValueError):
        _fail("malformed-styles-content-type", "workbook", "content-type", "xml")
    if root.tag != _TYPES: _fail("invalid-styles-content-type", "workbook", "root", str(root.tag))
    parts: set[CanonicalPartURI] = set()
    for child in root:
        if child.tag != _OVERRIDE or child.attrib.get("ContentType") != _STYLES_CONTENT_TYPE:
            continue
        if set(child.attrib) != {"PartName", "ContentType"}:
            _fail("invalid-styles-content-type", "workbook", "Override", "attribute")
        raw = child.attrib["PartName"]
        if not raw.startswith("/"):
            _fail("invalid-styles-content-type", "workbook", "PartName", raw)
        try: part = canonicalize_part_uri(raw[1:])
        except OPCPartURIError: _fail("invalid-styles-content-type", "workbook", "PartName", raw)
        if raw != f"/{part.value}":
            _fail("noncanonical-styles-content-type", part.value, "PartName", raw)
        parts.add(part)
    return frozenset(parts)

def _content_type(path: str, part: CanonicalPartURI) -> None:
    try:
        with ZipFile(path) as zf: payload = zf.read("[Content_Types].xml")
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error: _fail("unreadable-styles-content-type", part.value, "content-type", type(error).__name__)
    try: root = ET.fromstring(payload)
    except (ET.ParseError, LookupError, UnicodeError, ValueError): _fail("malformed-styles-content-type", part.value, "content-type", "xml")
    if root.tag != _TYPES: _fail("invalid-styles-content-type", part.value, "root", str(root.tag))
    expected = f"/{part.value}"; values=[]
    for child in root:
        if child.tag != _OVERRIDE: continue
        if set(child.attrib) != {"PartName", "ContentType"}: _fail("invalid-styles-content-type", part.value, "Override", "attribute")
        raw = child.attrib["PartName"]
        try: canonical = canonicalize_part_uri(raw[1:]) if raw.startswith("/") else None
        except OPCPartURIError: canonical = None
        if canonical == part:
            if raw != expected: _fail("noncanonical-styles-content-type", part.value, "PartName", raw)
            values.append(child.attrib["ContentType"])
    if not values: _fail("missing-styles-content-type", part.value, "PartName", expected)
    if len(values) != 1: _fail("ambiguous-styles-content-type", part.value, "PartName", expected)
    if values[0] != _STYLES_CONTENT_TYPE: _fail("wrong-styles-content-type", part.value, "ContentType", values[0])

def _usage(cells: WorkbookCellSemantics, table: StyleTable) -> tuple[WorksheetStyleUsage, ...]:
    output=[]
    for sheet in cells.worksheets:
        records=[]
        for cell in sheet.cells:
            # The accepted cell reader intentionally does not preserve @s. Read exact source only from its immutable projection is impossible;
            # it represents style metadata syntactically only. This reader resolves explicit attributes in a second strict package pass below.
            pass
        output.append(WorksheetStyleUsage(sheet.worksheet.name, sheet.worksheet.worksheet_part, tuple(records)))
    return tuple(output)

def _explicit_usage(path: str, cells: WorkbookCellSemantics, table: StyleTable) -> tuple[WorksheetStyleUsage, ...]:
    # Package graph already validates unique canonical members; collect only c@s in dependency worksheet order.
    requested = {sheet.worksheet.worksheet_part for sheet in cells.worksheets}
    try:
        with ZipFile(path) as archive:
            members = {}
            for info in archive.infolist():
                try: canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError: _fail("unreadable-styles-part", "workbook", "member", "invalid-member-name")
                if canonical in requested: members[canonical] = archive.read(info)
    except OPCStyleSemanticReaderError: raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error: _fail("unreadable-styles-part", "workbook", "member", type(error).__name__)
    if set(members) != requested: _fail("missing-worksheet-member", "workbook", "member", "projection")
    result=[]
    for sheet in cells.worksheets:
        payload = members[sheet.worksheet.worksheet_part]
        root = _xml_worksheet(payload, sheet.worksheet.worksheet_part)
        records=[]; direct_cells=[]
        sheet_data = [child for child in root if child.tag == f"{{{_SML}}}sheetData"]
        if len(sheet_data) != 1: _fail("invalid-styles-content", sheet.worksheet.worksheet_part.value, "sheetData", "structure")
        for row in sheet_data[0]:
            if row.tag != f"{{{_SML}}}row": _fail("invalid-styles-content", sheet.worksheet.worksheet_part.value, "sheetData", "child")
            for cell in row:
                if cell.tag != f"{{{_SML}}}c": _fail("invalid-styles-content", sheet.worksheet.worksheet_part.value, "row", "child")
                direct_cells.append(cell)
        direct_ids = {id(cell) for cell in direct_cells}
        for cell in root.iter(f"{{{_SML}}}c"):
            if id(cell) not in direct_ids: _fail("invalid-styles-content", sheet.worksheet.worksheet_part.value, "cell", "nested")
        if tuple(cell.attrib.get("r", "") for cell in direct_cells) != tuple(item.coordinate for item in sheet.cells):
            _fail("invalid-styles-content", sheet.worksheet.worksheet_part.value, "cell", "projection-mismatch")
        projection = {item.coordinate: item for item in sheet.cells}
        for cell in direct_cells:
            if "s" in cell.attrib:
                index = _uint(cell.attrib["s"], sheet.worksheet.worksheet_part.value, "s")
                if index >= len(table.cell_xfs): _fail("invalid-cell-style-reference", sheet.worksheet.worksheet_part.value, "s", cell.attrib["s"])
                coord = cell.attrib.get("r", "")
                # Cell syntax/order/A1 contract was accepted by the cell reader called first; map its immutable cell projection.
                found = projection.get(coord)
                if found is None: _fail("invalid-styles-content", sheet.worksheet.worksheet_part.value, "s", "unmapped-cell")
                records.append(CellStyleUse(found.coordinate, found.row, found.column, index))
        result.append(WorksheetStyleUsage(sheet.worksheet.name, sheet.worksheet.worksheet_part, tuple(records)))
    return tuple(result)

def _xml_worksheet(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    try: root = ET.fromstring(payload)
    except (ET.ParseError, LookupError, UnicodeError, ValueError): _fail("invalid-styles-content", part.value, "worksheet", "xml")
    return root

def read_workbook_style_semantics(package_path: os.PathLike[str] | str) -> WorkbookStyleSemantics:
    """Resolve strict native style definitions and explicit worksheet cell-style uses."""
    path = _coerce_path(package_path)
    topology = read_workbook_topology(path)
    cells = read_worksheet_cell_semantics(path)
    part = _styles_relationship(topology, path)
    _content_type(path, part)
    table = _table(_xml(_read_member(path, part, raw_exact=True), part), part)
    return WorkbookStyleSemantics(part, table, _explicit_usage(path, cells, table))
