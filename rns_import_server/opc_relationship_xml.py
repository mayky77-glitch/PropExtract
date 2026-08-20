"""Strict parser for OPC relationship XML parts.

This module validates only the relationship-part XML contract.  Resolving an
internal target against an OPC source part belongs to the package resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Final
from xml.etree import ElementTree as ET


RELATIONSHIPS_NAMESPACE: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_ROOT_TAG: Final = f"{{{RELATIONSHIPS_NAMESPACE}}}Relationships"
_RELATIONSHIP_TAG: Final = f"{{{RELATIONSHIPS_NAMESPACE}}}Relationship"
_REQUIRED_ATTRIBUTES: Final = frozenset({"Id", "Type", "Target"})
_ALLOWED_ATTRIBUTES: Final = _REQUIRED_ATTRIBUTES | {"TargetMode"}
_TARGET_MODES: Final = frozenset({"Internal", "External"})
_URI_SCHEME: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_PERCENT_ESCAPE: Final = re.compile(r"%[0-9A-Fa-f]{2}")
_IPV_FUTURE: Final = re.compile(r"v[0-9A-Fa-f]+\.[A-Za-z0-9._~!$&'()*+,;=:-]+")
_UNRESERVED: Final = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_SUB_DELIMS: Final = frozenset("!$&'()*+,;=")


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


def _has_valid_percent_escapes(value: str) -> bool:
    return all(
        character != "%" or _PERCENT_ESCAPE.fullmatch(value[position : position + 3]) is not None
        for position, character in enumerate(value)
    )


def _is_pchar(character: str) -> bool:
    return character in _UNRESERVED or character in _SUB_DELIMS or character in {":", "@", "%"}


def _is_valid_path(value: str, *, no_colon_first_segment: bool = False) -> bool:
    if not _has_valid_percent_escapes(value) or any(character != "/" and not _is_pchar(character) for character in value):
        return False
    if no_colon_first_segment and ":" in value.partition("/")[0]:
        return False
    return True


def _is_valid_authority(value: str) -> bool:
    userinfo, separator, host_port = value.rpartition("@")
    if separator:
        if "@" in userinfo or not _has_valid_percent_escapes(userinfo):
            return False
        if any(not (character in _UNRESERVED or character in _SUB_DELIMS or character in {":", "%"}) for character in userinfo):
            return False
    else:
        host_port = value
    if host_port.startswith("["):
        closing = host_port.find("]")
        if closing < 0:
            return False
        host = host_port[1:closing]
        remainder = host_port[closing + 1 :]
        if not host or (remainder and not remainder.startswith(":")):
            return False
        if host.startswith("v"):
            if _IPV_FUTURE.fullmatch(host) is None:
                return False
        else:
            try:
                ipaddress.IPv6Address(host)
            except ValueError:
                return False
        port = remainder[1:] if remainder else ""
    else:
        if "[" in host_port or "]" in host_port:
            return False
        if host_port.count(":") > 1:
            return False
        host, separator, port = host_port.partition(":")
        if host and all(character.isascii() and (character.isdigit() or character == ".") for character in host):
            try:
                ipaddress.IPv4Address(host)
            except ValueError:
                return False
        elif not _has_valid_percent_escapes(host) or any(
            character not in _UNRESERVED and character not in _SUB_DELIMS and character != "%"
            for character in host
        ):
            return False
        if not separator:
            port = ""
    return port.isdigit() or not port


def _split_uri_reference(value: str) -> tuple[str | None, str, str | None, str | None] | None:
    if not value or any(ord(character) <= 0x20 or ord(character) == 0x7F for character in value):
        return None
    if any(ord(character) > 0x7F or character in {'\\', '"', '<', '>', '^', '`', '{', '|', '}'} for character in value):
        return None
    if value.count("#") > 1:
        return None
    before_fragment, separator, fragment = value.partition("#")
    fragment = fragment if separator else None
    before_query, separator, query = before_fragment.partition("?")
    query = query if separator else None
    scheme_match = _URI_SCHEME.match(before_query)
    scheme = scheme_match.group()[:-1] if scheme_match else None
    path_part = before_query[len(scheme) + 1 :] if scheme else before_query
    if not _has_valid_percent_escapes(before_query):
        return None
    if query is not None and (not _has_valid_percent_escapes(query) or any(not _is_pchar(character) and character not in {"/", "?"} for character in query)):
        return None
    if fragment is not None and (not _has_valid_percent_escapes(fragment) or any(not _is_pchar(character) and character not in {"/", "?"} for character in fragment)):
        return None
    if path_part.startswith("//"):
        authority, slash, path = path_part[2:].partition("/")
        if not _is_valid_authority(authority) or not _is_valid_path(path if slash else ""):
            return None
    elif path_part.startswith("/"):
        if not _is_valid_path(path_part):
            return None
    elif not _is_valid_path(path_part, no_colon_first_segment=scheme is None):
        return None
    return (scheme, path_part, query, fragment)


def _is_absolute_uri_without_fragment(value: str) -> bool:
    parsed = _split_uri_reference(value)
    return parsed is not None and parsed[0] is not None and parsed[3] is None


def _is_absolute_uri(value: str) -> bool:
    parsed = _split_uri_reference(value)
    return parsed is not None and parsed[0] is not None


def _is_relative_uri_reference(value: str) -> bool:
    parsed = _split_uri_reference(value)
    return parsed is not None and parsed[0] is None and not parsed[1].startswith("/")


def _require_attributes(part: str, attributes: dict[str, str]) -> None:
    unknown = sorted(set(attributes) - _ALLOWED_ATTRIBUTES)
    if unknown:
        _fail("unknown-relationship-attribute", part, unknown[0])
    missing = sorted(_REQUIRED_ATTRIBUTES - set(attributes))
    if missing:
        _fail("missing-relationship-attribute", part, missing[0])
    for name in sorted(_REQUIRED_ATTRIBUTES - {"Target"}):
        if not attributes[name]:
            _fail("empty-relationship-attribute", part, name)


def _has_non_whitespace_text(element: ET.Element) -> bool:
    return bool(element.text and not element.text.isspace())


def _contains_doctype(payload: bytes | str) -> bool:
    if isinstance(payload, str):
        return "<!DOCTYPE" in payload
    return b"<!DOCTYPE" in payload.replace(b"\x00", b"")


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
    if _contains_doctype(payload):
        _fail("forbidden-doctype", part, "doctype")
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
        if child.tail and not child.tail.isspace():
            _fail("invalid-relationships-content", part, "tail")
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
        target = child.attrib["Target"]
        if _split_uri_reference(target) is None:
            _fail("invalid-relationship-target", part, target)
        if target_mode == "Internal" and not _is_relative_uri_reference(target):
            _fail("internal-target-not-relative", part, target)
        if target_mode == "External" and not _is_absolute_uri(target):
            _fail("external-target-not-absolute", part, target)
        seen_ids.add(relationship_id)
        records.append(Relationship(relationship_id, type_uri, target, target_mode))
    return tuple(records)
