"""Strict namespace-aware OPC part and relationship resolver."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from re import fullmatch
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class OPCResolverError(ValueError):
    code: str
    part: str
    detail: str
    def __str__(self) -> str: return f"{self.code}: {self.part}: {self.detail}"


@dataclass(frozen=True)
class ContentType:
    part: str | None
    extension: str | None
    value: str


@dataclass(frozen=True)
class Relationship:
    source: str | None
    id: str
    type: str
    mode: str
    target: str
    resolved_target: str | None


@dataclass(frozen=True)
class OPCPackage:
    contract_version: str
    parts: tuple[str, ...]
    content_types: tuple[ContentType, ...]
    relationships: tuple[Relationship, ...]


def _fail(code: str, part: str, detail: str) -> None:
    raise OPCResolverError(code, part, detail)


def _validate_uri(value: str, part: str) -> None:
    if not value or "\\" in value or any(ord(char) < 32 or char.isspace() for char in value): _fail("invalid-uri", part, value)
    for piece in value.split("%")[1:]:
        if len(piece) < 2 or fullmatch(r"[0-9A-Fa-f]{2}", piece[:2]) is None: _fail("invalid-percent-escape", part, value)
    decoded = unquote(value)
    if "\\" in decoded or any(ord(char) < 32 for char in decoded): _fail("invalid-uri", part, value)
    if "%" in value and any(segment in {".", ".."} for segment in decoded.split("/")): _fail("encoded-traversal", part, value)


def _canonical_part(value: str, part: str) -> str:
    _validate_uri(value, part)
    if value.startswith("/") or "?" in value or "#" in value or urlsplit(value).scheme or urlsplit(value).netloc: _fail("invalid-part-uri", part, value)
    stack: list[str] = []
    for segment in value.split("/"):
        if segment in {"", "."}: continue
        if segment == "..":
            if not stack: _fail("package-root-escape", part, value)
            stack.pop()
        else: stack.append(segment)
    if not stack: _fail("invalid-part-uri", part, value)
    return "/".join(stack)


def _parse_xml(raw: bytes, part: str) -> ET.Element:
    try: return ET.fromstring(raw)
    except ET.ParseError as error: _fail("malformed-xml", part, str(error))


def _source_for_rels(part: str) -> str | None:
    if part == "_rels/.rels": return None
    path = PurePosixPath(part)
    if path.parent.name != "_rels" or not path.name.endswith(".rels"): _fail("invalid-relationship-part", part, part)
    return str(path.parent.parent / path.name[:-5])


def _resolve(source: str | None, target: str) -> str:
    _validate_uri(target, source or "_rels/.rels")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or target.startswith("/"): _fail("invalid-internal-target", source or "_rels/.rels", target)
    base = "" if source is None else str(PurePosixPath(source).parent)
    return _canonical_part(f"{base}/{target}" if base else target, source or "_rels/.rels")


def _external(target: str, part: str) -> None:
    _validate_uri(target, part)
    parsed = urlsplit(target)
    if not parsed.scheme or (parsed.scheme.lower() in {"http", "https", "ftp"} and not parsed.netloc): _fail("invalid-external-target", part, target)


def _content_types(raw: bytes) -> tuple[ContentType, ...]:
    root = _parse_xml(raw, "[Content_Types].xml")
    if root.tag != f"{{{CT}}}Types": _fail("invalid-content-types", "[Content_Types].xml", root.tag)
    items: list[ContentType] = []
    for node in root:
        value = node.get("ContentType")
        if node.tag == f"{{{CT}}}Default":
            if not value or not node.get("Extension"): _fail("invalid-content-type", "[Content_Types].xml", ET.tostring(node, encoding="unicode"))
            items.append(ContentType(None, node.get("Extension"), value))
        elif node.tag == f"{{{CT}}}Override":
            name = node.get("PartName")
            if not value or not name or not name.startswith("/"): _fail("invalid-content-type", "[Content_Types].xml", ET.tostring(node, encoding="unicode"))
            items.append(ContentType(_canonical_part(name[1:], "[Content_Types].xml"), None, value))
    return tuple(items)


def resolve_opc_package(path: str) -> OPCPackage:
    with ZipFile(path) as archive:
        raw_parts: dict[str, bytes] = {}
        for member in archive.infolist():
            canonical = _canonical_part(member.filename, member.filename)
            if canonical in raw_parts: _fail("duplicate-normalized-part", canonical, member.filename)
            raw_parts[canonical] = archive.read(member)
    if "[Content_Types].xml" not in raw_parts or "_rels/.rels" not in raw_parts: _fail("missing-opc-root", "", "[Content_Types].xml or _rels/.rels")
    content_types = _content_types(raw_parts["[Content_Types].xml"])
    relationships: list[Relationship] = []
    for rel_part in sorted(part for part in raw_parts if part.endswith(".rels")):
        source = _source_for_rels(rel_part)
        root = _parse_xml(raw_parts[rel_part], rel_part)
        if root.tag != f"{{{PR}}}Relationships": _fail("malformed-relationships", rel_part, root.tag)
        seen: set[str] = set()
        for node in root.findall(f"{{{PR}}}Relationship"):
            ident, type_, target, mode = node.get("Id"), node.get("Type"), node.get("Target"), node.get("TargetMode", "Internal")
            if not ident or not type_ or target is None or ident in seen or mode not in {"Internal", "External"}: _fail("malformed-relationship", rel_part, ET.tostring(node, encoding="unicode"))
            seen.add(ident)
            if mode == "External": _external(target, rel_part); resolved = None
            else:
                resolved = _resolve(source, target)
                if resolved not in raw_parts: _fail("missing-target", rel_part, resolved)
            relationships.append(Relationship(source, ident, type_, mode, target, resolved))
    return OPCPackage("opc-package-resolver-v1", tuple(sorted(raw_parts)), content_types, tuple(relationships))
