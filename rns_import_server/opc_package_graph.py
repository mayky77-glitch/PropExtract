"""Build a strict, immutable graph for an OPC ZIP package.

The graph intentionally stops at package structure.  Content-type semantics
and application-specific relationship handling belong to later layers.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile, ZipInfo

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri, resolve_relative_part_uri
from .opc_relationship_xml import OPCRelationshipXMLError, parse_relationship_xml


CONTENT_TYPES_NAME: Final = "[Content_Types].xml"
CONTENT_TYPES_NAMESPACE: Final = "http://schemas.openxmlformats.org/package/2006/content-types"
_CONTENT_TYPES_TAG: Final = f"{{{CONTENT_TYPES_NAMESPACE}}}Types"


@dataclass(frozen=True)
class PackagePart:
    """A non-control, non-relationship OPC package part."""

    name: CanonicalPartURI


@dataclass(frozen=True)
class PackageRelationship:
    """One relationship, preserving relationship-part and XML order."""

    relationship_part: CanonicalPartURI
    source: CanonicalPartURI | None
    id: str
    type_uri: str
    target: str
    target_mode: str
    resolved_target: CanonicalPartURI | None

    @property
    def source_part(self) -> CanonicalPartURI | None:
        """Explicit alias for callers that name the source as a part."""
        return self.source

    @property
    def resolved_target_part(self) -> CanonicalPartURI | None:
        """Explicit alias for the internal resolved target."""
        return self.resolved_target


@dataclass(frozen=True)
class OPCPackageGraph:
    """Read-only package parts and relationships in ZIP/XML source order."""

    parts: tuple[PackagePart, ...]
    relationships: tuple[PackageRelationship, ...]


@dataclass
class OPCPackageGraphError(ValueError):
    """Stable package-graph failure with enough context for a caller to act."""

    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def __str__(self) -> str:
        return ": ".join(self.as_tuple())

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCPackageGraphError(code, subject, field, detail)


def _package_subject(package_path: os.PathLike[str] | str) -> str:
    try:
        return os.fspath(package_path)
    except TypeError:
        return str(package_path)


def _read_member(package: ZipFile, info: ZipInfo, package_subject: str) -> bytes:
    try:
        return package.read(info)
    except (BadZipFile, NotImplementedError, OSError, RuntimeError) as error:
        _fail("bad-zip-member", info.filename, "member", type(error).__name__)
    raise AssertionError("unreachable")


def _validate_content_types(payload: bytes, package_subject: str) -> None:
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, UnicodeError, ValueError) as error:
        _fail("malformed-content-types", package_subject, "content-types", type(error).__name__)
    if root.tag != _CONTENT_TYPES_TAG:
        _fail("invalid-content-types-root", package_subject, "content-types", str(root.tag))


def _canonical_members(infos: tuple[ZipInfo, ...]) -> tuple[tuple[ZipInfo, CanonicalPartURI], ...]:
    canonical: list[tuple[ZipInfo, CanonicalPartURI]] = []
    seen: dict[str, str] = {}
    for info in infos:
        if info.filename == CONTENT_TYPES_NAME:
            continue
        try:
            name = canonicalize_part_uri(info.filename)
        except OPCPartURIError as error:
            _fail("invalid-part-uri", info.filename, "name", error.code)
        first = seen.get(name.value)
        if first is not None:
            _fail("duplicate-normalized-part", name.value, "name", info.filename)
        seen[name.value] = info.filename
        canonical.append((info, name))
    return tuple(canonical)


def _relationship_source(relationship_part: CanonicalPartURI) -> CanonicalPartURI | None:
    name = relationship_part.value
    if name == "_rels/.rels":
        return None
    segments = name.split("/")
    if len(segments) < 3 or segments[-2] != "_rels" or not segments[-1].endswith(".rels"):
        _fail("misplaced-relationship-part", name, "name", name)
    basename = segments[-1].removesuffix(".rels")
    if not basename:
        _fail("misplaced-relationship-part", name, "name", name)
    source_name = "/".join((*segments[:-2], basename))
    try:
        return canonicalize_part_uri(source_name)
    except OPCPartURIError as error:
        _fail("invalid-relationship-source", name, "source", error.detail)
    raise AssertionError("unreachable")


def _relationship_parts(
    members: tuple[tuple[ZipInfo, CanonicalPartURI], ...],
) -> tuple[tuple[ZipInfo, CanonicalPartURI, CanonicalPartURI | None], ...]:
    relationship_parts: list[tuple[ZipInfo, CanonicalPartURI, CanonicalPartURI | None]] = []
    for info, name in members:
        if not name.value.endswith(".rels"):
            continue
        relationship_parts.append((info, name, _relationship_source(name)))
    return tuple(relationship_parts)


def build_opc_package_graph(package_path: os.PathLike[str] | str) -> OPCPackageGraph:
    """Read and validate an OPC package without extracting any members."""
    package_subject = _package_subject(package_path)
    try:
        package = ZipFile(package_path)
    except TypeError:
        _fail("invalid-package-path", package_subject, "path", type(package_path).__name__)
    except (BadZipFile, LargeZipFile):
        _fail("invalid-zip-package", package_subject, "path", "not-a-zip")
    except OSError as error:
        _fail("unreadable-package", package_subject, "path", type(error).__name__)

    with package:
        infos = tuple(package.infolist())
        for info in infos:
            if info.is_dir() or info.filename.endswith("/"):
                _fail("directory-entry", info.filename, "name", "directory")
            if info.flag_bits & 0x1:
                _fail("encrypted-zip-member", info.filename, "member", "encrypted")

        content_types = tuple(info for info in infos if info.filename == CONTENT_TYPES_NAME)
        if not content_types:
            _fail("missing-content-types", package_subject, "content-types", CONTENT_TYPES_NAME)
        if len(content_types) != 1:
            _fail("duplicate-content-types", package_subject, "content-types", CONTENT_TYPES_NAME)

        try:
            bad_member = package.testzip()
        except (BadZipFile, NotImplementedError, OSError, RuntimeError) as error:
            _fail("bad-zip-member", package_subject, "member", type(error).__name__)
        if bad_member is not None:
            _fail("bad-zip-member", bad_member, "member", "crc")

        _validate_content_types(_read_member(package, content_types[0], package_subject), package_subject)
        members = _canonical_members(infos)
        relationship_parts = _relationship_parts(members)
        relationship_names = frozenset(name.value for _, name, _ in relationship_parts)
        parts = tuple(
            PackagePart(name)
            for _, name in members
            if not name.value.endswith(".rels")
        )
        part_names = frozenset(part.name.value for part in parts)

        relationships: list[PackageRelationship] = []
        for info, relationship_part, source in relationship_parts:
            if source is not None and source.value not in part_names:
                _fail("invalid-relationship-source", relationship_part.value, "source", source.value)
            payload = _read_member(package, info, package_subject)
            try:
                parsed = parse_relationship_xml(relationship_part.value, payload)
            except OPCRelationshipXMLError as error:
                _fail(error.code, relationship_part.value, "xml", error.detail)
            for relationship in parsed:
                resolved_target: CanonicalPartURI | None = None
                if relationship.target_mode == "Internal":
                    try:
                        resolved_target = resolve_relative_part_uri(source, relationship.target)
                    except OPCPartURIError:
                        _fail(
                            "invalid-relationship-target",
                            source.value if source is not None else relationship_part.value,
                            "Target",
                            relationship.target,
                        )
                    if resolved_target.value == CONTENT_TYPES_NAME or resolved_target.value in relationship_names:
                        _fail(
                            "forbidden-internal-target",
                            source.value if source is not None else relationship_part.value,
                            "Target",
                            relationship.target,
                        )
                    if resolved_target.value not in part_names:
                        _fail(
                            "missing-internal-target",
                            source.value if source is not None else relationship_part.value,
                            "Target",
                            relationship.target,
                        )
                relationships.append(
                    PackageRelationship(
                        relationship_part,
                        source,
                        relationship.id,
                        relationship.type_uri,
                        relationship.target,
                        relationship.target_mode,
                        resolved_target,
                    )
                )
    return OPCPackageGraph(parts, tuple(relationships))
