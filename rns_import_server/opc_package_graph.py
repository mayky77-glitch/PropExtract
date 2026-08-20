"""Deterministic, read-only graph construction for strict OPC ZIP packages."""
from __future__ import annotations

from dataclasses import dataclass
import lzma
import os
from pathlib import Path
import re
from typing import Final
from urllib.parse import unquote_to_bytes
from xml.etree import ElementTree as ET
import zlib
from zipfile import BadZipFile, LargeZipFile, ZipFile, ZipInfo

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri, resolve_relative_part_uri
from .opc_relationship_xml import OPCRelationshipXMLError, parse_relationship_xml


CONTENT_TYPES_NAME: Final = "[Content_Types].xml"
CONTENT_TYPES_NAMESPACE: Final = "http://schemas.openxmlformats.org/package/2006/content-types"
_CONTENT_TYPES_TAG: Final = f"{{{CONTENT_TYPES_NAMESPACE}}}Types"
_XML_DECLARATION_ENCODING: Final = re.compile(
    br'^<\?xml[\t\r\n ]+[^?]*?encoding[\t\r\n ]*=[\t\r\n ]*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_ZIP_MEMBER_ERRORS: Final = (
    BadZipFile,
    EOFError,
    NotImplementedError,
    OSError,
    RuntimeError,
    ValueError,
    zlib.error,
    lzma.LZMAError,
)


@dataclass(frozen=True)
class PackagePart:
    name: CanonicalPartURI


@dataclass(frozen=True)
class PackageRelationship:
    relationship_part: CanonicalPartURI
    source: CanonicalPartURI | None
    id: str
    type_uri: str
    target: str
    target_mode: str
    resolved_target: CanonicalPartURI | None

    @property
    def source_part(self) -> CanonicalPartURI | None:
        return self.source


@dataclass(frozen=True)
class OPCPackageGraph:
    parts: tuple[PackagePart, ...]
    relationships: tuple[PackageRelationship, ...]


@dataclass
class OPCPackageGraphError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCPackageGraphError(code, subject, field, detail)


def _safe_path_subject(package_path: object) -> str:
    path_type = type(package_path)
    return f"{path_type.__module__}.{path_type.__qualname__}"


def _coerce_package_path(package_path: os.PathLike[str] | str) -> str:
    subject = _safe_path_subject(package_path)
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


def _raw_relationship_source(name: str) -> str | None:
    if name == "_rels/.rels":
        return None
    if name.startswith("_rels/") and name.endswith(".rels"):
        filename = name.removeprefix("_rels/").removesuffix(".rels")
        if "/" in filename:
            return filename if any(segment in {".", ".."} for segment in filename.split("/")) else ""
        return filename or ""
    if "/_rels/" in name and name.endswith(".rels"):
        directory, filename = name.split("/_rels/", 1)
        filename = filename.removesuffix(".rels")
        if "/" in filename and any(segment in {".", ".."} for segment in filename.split("/")):
            return f"{directory}/{filename}"
        if not directory or not filename or "/" in filename or "/_rels/" in directory:
            return ""
        return f"{directory}/{filename}"
    return ""


def _canonicalize_member(info: ZipInfo) -> CanonicalPartURI:
    raw_source = _raw_relationship_source(info.filename)
    if raw_source not in {None, ""}:
        try:
            canonicalize_part_uri(raw_source)
        except OPCPartURIError:
            _fail("invalid-relationship-source", info.filename, "source", raw_source)
    try:
        return canonicalize_part_uri(info.filename)
    except OPCPartURIError as error:
        _fail("invalid-part-uri", info.filename, "name", error.code)
    raise AssertionError("unreachable")


def _reject_parser_unsupported_xml_encoding(payload: bytes, subject: str, field: str) -> None:
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    match = _XML_DECLARATION_ENCODING.match(candidate)
    if match is None:
        return
    try:
        ET.fromstring(payload)
    except (LookupError, ValueError):
        _fail("unsupported-xml-encoding", subject, field, "encoding")


def _validate_content_types(payload: bytes, package_subject: str) -> None:
    _reject_parser_unsupported_xml_encoding(payload, package_subject, "content-types")
    try:
        root = ET.fromstring(payload)
    except LookupError:
        _fail("unsupported-xml-encoding", package_subject, "content-types", "encoding")
    except (ET.ParseError, UnicodeError, ValueError):
        _fail("malformed-content-types", package_subject, "content-types", "xml")
    if root.tag != _CONTENT_TYPES_TAG:
        _fail("invalid-content-types-root", package_subject, "content-types", str(root.tag))


def _source_for_relationship_part(name: CanonicalPartURI) -> CanonicalPartURI | None:
    raw_source = _raw_relationship_source(name.value)
    if raw_source is None:
        return None
    if not raw_source:
        _fail("misplaced-relationship-part", name.value, "name", name.value)
    try:
        return canonicalize_part_uri(raw_source)
    except OPCPartURIError:
        _fail("invalid-relationship-source", name.value, "source", raw_source)
    raise AssertionError("unreachable")


def _relationship_error(error: OPCRelationshipXMLError, part: CanonicalPartURI, source: CanonicalPartURI | None) -> None:
    context = source.value if source is not None else part.value
    field_by_code = {
        "invalid-relationship-id": "Id",
        "invalid-relationship-type": "Type",
        "invalid-relationship-target": "Target",
        "internal-target-not-relative": "Target",
        "invalid-target-mode": "TargetMode",
    }
    if error.code == "missing-relationship-attribute":
        _fail(error.code, part.value, error.detail, "")
    if error.code == "invalid-relationships-root" and error.detail.startswith("{"):
        namespace = error.detail[1:].partition("}")[0]
        _fail("invalid-relationships-namespace", part.value, "namespace", namespace)
    _fail(error.code, context, field_by_code.get(error.code, "xml"), error.detail)


def _read_member(package: ZipFile, info: ZipInfo) -> bytes:
    try:
        return package.read(info)
    except _ZIP_MEMBER_ERRORS as error:
        _fail("bad-zip-member", info.filename, "member", type(error).__name__)
    raise AssertionError("unreachable")


def _validate_zip_members(package: ZipFile, infos: tuple[ZipInfo, ...]) -> None:
    for info in infos:
        try:
            with package.open(info) as member:
                while member.read(1024 * 1024):
                    pass
        except _ZIP_MEMBER_ERRORS as error:
            _fail("bad-zip-member", info.filename, "member", type(error).__name__)


def _is_content_types_target(name: CanonicalPartURI) -> bool:
    if name.value == CONTENT_TYPES_NAME:
        return True
    try:
        return unquote_to_bytes(name.value).decode("utf-8") == CONTENT_TYPES_NAME
    except UnicodeDecodeError:
        return False


def build_opc_package_graph(package_path: os.PathLike[str] | str) -> OPCPackageGraph:
    """Return a fully validated graph, or one stable typed failure."""
    path = _coerce_package_path(package_path)
    subject = path
    try:
        package = ZipFile(path)
    except (BadZipFile, LargeZipFile):
        _fail("invalid-zip-package", subject, "path", "not-a-zip")
    except ValueError as error:
        _fail("unreadable-package", subject, "path", "embedded-nul" if "null" in str(error).lower() else type(error).__name__)
    except OSError as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)

    with package:
        infos = tuple(package.infolist())
        canonical_members: list[tuple[ZipInfo, CanonicalPartURI]] = []
        seen: dict[str, str] = {}
        control_info: ZipInfo | None = None
        for info in infos:
            if info.is_dir() or info.filename.endswith("/"):
                _fail("directory-entry", info.filename, "name", "directory")
            if info.flag_bits & 0x1:
                _fail("encrypted-zip-member", info.filename, "member", "encrypted")
            canonical = _canonicalize_member(info)
            first = seen.get(canonical.value)
            if first is not None:
                _fail("duplicate-normalized-part", canonical.value, "name", info.filename)
            seen[canonical.value] = info.filename
            if canonical.value == CONTENT_TYPES_NAME:
                if info.filename != CONTENT_TYPES_NAME:
                    _fail("content-types-alias", info.filename, "name", CONTENT_TYPES_NAME)
                control_info = info
            else:
                canonical_members.append((info, canonical))

        if control_info is None:
            _fail("missing-content-types", subject, "content-types", CONTENT_TYPES_NAME)
        _validate_zip_members(package, infos)
        _validate_content_types(_read_member(package, control_info), subject)

        relationship_parts: list[tuple[ZipInfo, CanonicalPartURI, CanonicalPartURI | None]] = []
        parts: list[PackagePart] = []
        for info, name in canonical_members:
            if name.value.endswith(".rels"):
                relationship_parts.append((info, name, _source_for_relationship_part(name)))
            else:
                parts.append(PackagePart(name))
        part_names = frozenset(part.name.value for part in parts)
        relationship_names = frozenset(name.value for _, name, _ in relationship_parts)

        relationships: list[PackageRelationship] = []
        for info, relationship_part, source in relationship_parts:
            if source is not None and source.value not in part_names:
                _fail("invalid-relationship-source", relationship_part.value, "source", source.value)
            try:
                payload = _read_member(package, info)
                _reject_parser_unsupported_xml_encoding(payload, relationship_part.value, "xml")
                parsed = parse_relationship_xml(relationship_part.value, payload)
            except OPCRelationshipXMLError as error:
                _relationship_error(error, relationship_part, source)
            except LookupError:
                _fail("unsupported-xml-encoding", relationship_part.value, "xml", "encoding")
            for relationship in parsed:
                resolved: CanonicalPartURI | None = None
                if relationship.target_mode == "Internal":
                    try:
                        resolved = resolve_relative_part_uri(source, relationship.target)
                    except OPCPartURIError:
                        _fail("invalid-relationship-target", source.value if source else relationship_part.value, "Target", relationship.target)
                    if _is_content_types_target(resolved) or resolved.value in relationship_names:
                        _fail("forbidden-internal-target", source.value if source else relationship_part.value, "Target", relationship.target)
                    if resolved.value not in part_names:
                        _fail("missing-internal-target", source.value if source else relationship_part.value, "Target", relationship.target)
                relationships.append(PackageRelationship(relationship_part, source, relationship.id, relationship.type_uri, relationship.target, relationship.target_mode, resolved))
    return OPCPackageGraph(tuple(parts), tuple(relationships))
