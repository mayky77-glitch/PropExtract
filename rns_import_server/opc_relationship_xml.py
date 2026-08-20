"""Strict parser for OPC relationship XML parts.

This module validates only the relationship-part XML contract.  Resolving an
internal target against an OPC source part belongs to the package resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET


RELATIONSHIPS_NAMESPACE: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_ROOT_TAG: Final = f"{{{RELATIONSHIPS_NAMESPACE}}}Relationships"
_RELATIONSHIP_TAG: Final = f"{{{RELATIONSHIPS_NAMESPACE}}}Relationship"
_REQUIRED_ATTRIBUTES: Final = frozenset({"Id", "Type", "Target"})
_ALLOWED_ATTRIBUTES: Final = _REQUIRED_ATTRIBUTES | {"TargetMode"}
_TARGET_MODES: Final = frozenset({"Internal", "External"})
_URI_SCHEME: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_PERCENT_ESCAPE: Final = re.compile(r"%[0-9A-Fa-f]{2}")


@dataclass(frozen=True)
class Relationship:
    """One validated relationship, in source XML order."""

    id: str
    type_uri: str
    target: str
    target_mode: str


@dataclass(frozen=True)
class OPCRelationshipXMLError(ValueError):
    """Stable relationship XML validation failure."""

    code: str
    part: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.part, self.detail)

    def __str__(self) -> str:
        return ": ".join(self.as_tuple())

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.code, self.part, self.detail)


def _fail(code: str, part: str, detail: str) -> None:
    raise OPCRelationshipXMLError(code, part, detail)


def _is_ncname(value: str) -> bool:
    """Apply XML 1.0 Fifth Edition NCName production, excluding colon."""
    if not value:
        return False
    return _is_ncname_start(ord(value[0])) and all(_is_ncname_char(ord(character)) for character in value[1:])


def _is_ncname_start(character: int) -> bool:
    return (
        character == 0x5F
        or 0x41 <= character <= 0x5A
        or 0x61 <= character <= 0x7A
        or 0xC0 <= character <= 0xD6
        or 0xD8 <= character <= 0xF6
        or 0xF8 <= character <= 0x2FF
        or 0x370 <= character <= 0x37D
        or 0x37F <= character <= 0x1FFF
        or 0x200C <= character <= 0x200D
        or 0x2070 <= character <= 0x218F
        or 0x2C00 <= character <= 0x2FEF
        or 0x3001 <= character <= 0xD7FF
        or 0xF900 <= character <= 0xFDCF
        or 0xFDF0 <= character <= 0xFFFD
        or 0x10000 <= character <= 0xEFFFF
    )


def _is_ncname_char(character: int) -> bool:
    return (
        _is_ncname_start(character)
        or character in {0x2D, 0x2E, 0xB7}
        or 0x30 <= character <= 0x39
        or 0x300 <= character <= 0x36F
        or 0x203F <= character <= 0x2040
    )


def _is_absolute_uri_without_fragment(value: str) -> bool:
    if not value or any(ord(character) <= 0x20 or ord(character) == 0x7F for character in value):
        return False
    if any(ord(character) > 0x7F or character in {'\\', '"', '<', '>', '^', '`', '{', '|', '}'} for character in value):
        return False
    if _URI_SCHEME.match(value) is None or "#" in value:
        return False
    for position, character in enumerate(value):
        if character == "%" and _PERCENT_ESCAPE.fullmatch(value[position : position + 3]) is None:
            return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(parsed.scheme) and not parsed.fragment


def _require_attributes(part: str, attributes: dict[str, str]) -> None:
    unknown = sorted(set(attributes) - _ALLOWED_ATTRIBUTES)
    if unknown:
        _fail("unknown-relationship-attribute", part, unknown[0])
    missing = sorted(_REQUIRED_ATTRIBUTES - set(attributes))
    if missing:
        _fail("missing-relationship-attribute", part, missing[0])
    for name in sorted(_REQUIRED_ATTRIBUTES):
        if not attributes[name]:
            _fail("empty-relationship-attribute", part, name)


def _has_non_whitespace_text(element: ET.Element) -> bool:
    return bool(element.text and not element.text.isspace())


def parse_relationship_xml(part: str, payload: bytes | str) -> tuple[Relationship, ...]:
    """Parse one OPC ``.rels`` part or raise a typed validation error.

    ``part`` is diagnostic context; it is retained verbatim in every error.
    ``TargetMode`` defaults to ``Internal`` as specified by OPC.  Returned
    records preserve document order and do not resolve target paths.
    """
    if not isinstance(part, str):
        _fail("invalid-part", str(part), type(part).__name__)
    if not isinstance(payload, (bytes, str)):
        _fail("invalid-xml-input", part, type(payload).__name__)
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, UnicodeError, ValueError):
        _fail("malformed-xml", part, "document")
    if root.tag != _ROOT_TAG:
        _fail("invalid-relationships-root", part, str(root.tag))
    if root.attrib:
        _fail("unknown-root-attribute", part, sorted(root.attrib)[0])
    if _has_non_whitespace_text(root):
        _fail("invalid-relationships-content", part, "text")

    seen_ids: set[str] = set()
    records: list[Relationship] = []
    for child in root:
        if child.tag != _RELATIONSHIP_TAG:
            _fail("invalid-relationships-child", part, str(child.tag))
        if _has_non_whitespace_text(child) or len(child):
            _fail("invalid-relationship-content", part, child.attrib.get("Id", "content"))
        _require_attributes(part, child.attrib)
        relationship_id = child.attrib["Id"]
        if not _is_ncname(relationship_id):
            _fail("invalid-relationship-id", part, relationship_id)
        if relationship_id in seen_ids:
            _fail("duplicate-relationship-id", part, relationship_id)
        type_uri = child.attrib["Type"]
        if not _is_absolute_uri_without_fragment(type_uri):
            _fail("invalid-relationship-type", part, type_uri)
        target_mode = child.attrib.get("TargetMode", "Internal")
        if target_mode not in _TARGET_MODES:
            _fail("invalid-target-mode", part, target_mode)
        seen_ids.add(relationship_id)
        records.append(Relationship(relationship_id, type_uri, child.attrib["Target"], target_mode))
    return tuple(records)
