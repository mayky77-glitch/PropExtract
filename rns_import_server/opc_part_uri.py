"""Strict, typed normalization for OPC package part URI paths.

OPC part names are package-relative URI paths.  This module deliberately keeps
them separate from relationship targets: a part cannot contain dot segments,
whereas a relative target may contain dot segments before it is resolved.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import unquote_to_bytes


_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_FORBIDDEN_RAW = frozenset("\\?#")


@dataclass(frozen=True)
class RawPartURI:
    """Untrusted package member name, retained for diagnostics."""

    value: str


@dataclass(frozen=True)
class CanonicalPartURI:
    """Validated, package-relative part path suitable for comparison/lookup."""

    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RelativePartURI:
    """Validated internal relationship target before source-relative resolution."""

    value: str


@dataclass(frozen=True)
class OPCPartURIError(ValueError):
    """Stable machine-readable validation failure."""

    code: str
    subject: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.detail)

    def __str__(self) -> str:
        return ": ".join(self.as_tuple())

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.code, self.subject, self.detail)


@dataclass(frozen=True)
class PartURICollision:
    """Two distinct raw member names normalizing to one canonical part name."""

    canonical: CanonicalPartURI
    first: RawPartURI
    second: RawPartURI

    def as_tuple(self) -> tuple[str, str, str, str]:
        return ("duplicate-normalized-part", self.canonical.value, self.first.value, self.second.value)


def _fail(code: str, subject: str, detail: str) -> None:
    raise OPCPartURIError(code, subject, detail)


def _coerce(value: str | RawPartURI | CanonicalPartURI | RelativePartURI, subject: str) -> str:
    if isinstance(value, (RawPartURI, CanonicalPartURI, RelativePartURI)):
        value = value.value
    if not isinstance(value, str):
        _fail("invalid-uri-type", subject, type(value).__name__)
    return value


def _validate_unicode(value: str, subject: str, detail: str | None = None) -> None:
    error_detail = value if detail is None else detail
    if not value:
        _fail("empty-uri", subject, error_detail)
    if value != unicodedata.normalize("NFC", value):
        _fail("ambiguous-unicode", subject, error_detail)
    for character in value:
        ordinal = ord(character)
        if ordinal <= 31 or ordinal == 127 or 128 <= ordinal <= 159:
            _fail("invalid-control", subject, error_detail)
        if unicodedata.category(character) in {"Cf", "Cs"}:
            _fail("ambiguous-unicode", subject, error_detail)


def _percent_normalize(value: str, subject: str) -> str:
    """Validate escapes and decode only RFC 3986 unreserved aliases."""
    _validate_unicode(value, subject)
    if "\\" in value:
        _fail("invalid-backslash", subject, value)
    position = 0
    output: list[str] = []
    while position < len(value):
        character = value[position]
        if character != "%":
            output.append(character)
            position += 1
            continue
        token = value[position : position + 3]
        if _PERCENT_ESCAPE.fullmatch(token) is None:
            _fail("invalid-percent-escape", subject, value)
        byte = int(token[1:], 16)
        if byte in {0x2F, 0x5C}:
            _fail("encoded-separator", subject, value)
        if byte <= 31 or byte == 127:
            _fail("invalid-control", subject, value)
        character_from_byte = chr(byte)
        if character_from_byte in _UNRESERVED:
            output.append(character_from_byte)
        else:
            output.append("%" + token[1:].upper())
        position += 3

    normalized = "".join(output)
    # Percent bytes must either be valid UTF-8 text or remain a deliberate
    # ASCII URI escape.  A malformed non-ASCII byte sequence is ambiguous.
    try:
        decoded = unquote_to_bytes(normalized).decode("utf-8")
    except UnicodeDecodeError:
        _fail("ambiguous-unicode", subject, value)
    _validate_unicode(decoded, subject, value)
    if "/" in decoded and "%2F" in normalized.upper():
        _fail("encoded-separator", subject, value)
    if "\\" in decoded:
        _fail("invalid-backslash", subject, value)
    return normalized


def _has_percent_decoded_dot_segment(raw: str, normalized: str) -> bool:
    """Return whether percent decoding, rather than raw syntax, made a dot segment."""
    return any(
        normalized_segment in {".", ".."} and raw_segment != normalized_segment
        for raw_segment, normalized_segment in zip(raw.split("/"), normalized.split("/"), strict=True)
    )


def _validate_path_chars(value: str, subject: str) -> None:
    if any(character in _FORBIDDEN_RAW for character in value):
        _fail("invalid-part-character", subject, value)
    if value.startswith("/") or value.endswith("/") or "//" in value:
        _fail("invalid-slash", subject, value)


def canonicalize_part_uri(value: str | RawPartURI | CanonicalPartURI) -> CanonicalPartURI:
    """Return strict canonical OPC part path, rejecting non-canonical topology."""
    raw = _coerce(value, "part")
    normalized = _percent_normalize(raw, raw)
    _validate_path_chars(normalized, raw)
    segments = normalized.split("/")
    if _has_percent_decoded_dot_segment(raw, normalized):
        _fail("encoded-traversal", raw, normalized)
    if any(segment in {"", ".", ".."} for segment in segments):
        _fail("invalid-part-segment", raw, normalized)
    return CanonicalPartURI(normalized)


def parse_relative_part_uri(value: str | RelativePartURI) -> RelativePartURI:
    """Validate relative internal relationship target without resolving it."""
    raw = _coerce(value, "target")
    normalized = _percent_normalize(raw, raw)
    if any(character in _FORBIDDEN_RAW for character in normalized):
        _fail("invalid-target-character", raw, normalized)
    if normalized.startswith("/") or normalized.endswith("/") or "//" in normalized:
        _fail("invalid-slash", raw, normalized)
    if _has_percent_decoded_dot_segment(raw, normalized):
        _fail("encoded-traversal", raw, normalized)
    if not normalized:
        _fail("empty-uri", raw, normalized)
    return RelativePartURI(normalized)


def resolve_relative_part_uri(
    source: str | CanonicalPartURI | None, target: str | RelativePartURI
) -> CanonicalPartURI:
    """Resolve internal target relative to source part, never above package root."""
    canonical_source = None if source is None else canonicalize_part_uri(source)
    relative = parse_relative_part_uri(target)
    if relative.value.split("/")[-1] in {".", ".."}:
        _fail("invalid-part-uri", relative.value, relative.value)
    stack = [] if canonical_source is None else canonical_source.value.split("/")[:-1]
    for segment in relative.value.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            if not stack:
                _fail("package-root-escape", relative.value, relative.value)
            stack.pop()
            continue
        stack.append(segment)
    if not stack:
        _fail("invalid-part-uri", relative.value, relative.value)
    return canonicalize_part_uri("/".join(stack))


def normalized_part_collisions(values: tuple[str | RawPartURI, ...] | list[str | RawPartURI]) -> tuple[PartURICollision, ...]:
    """Return deterministic collision evidence; never hide percent aliases."""
    seen: dict[str, RawPartURI] = {}
    collisions: list[PartURICollision] = []
    for value in values:
        raw_value = _coerce(value, "part")
        raw = RawPartURI(raw_value)
        canonical = canonicalize_part_uri(raw)
        first = seen.get(canonical.value)
        if first is None:
            seen[canonical.value] = raw
        else:
            collisions.append(PartURICollision(canonical, first, raw))
    return tuple(collisions)


def require_unique_part_uris(values: tuple[str | RawPartURI, ...] | list[str | RawPartURI]) -> tuple[CanonicalPartURI, ...]:
    """Canonicalize package member names, failing on first ordered collision."""
    canonical = tuple(canonicalize_part_uri(value) for value in values)
    collisions = normalized_part_collisions(values)
    if collisions:
        collision = collisions[0]
        raise OPCPartURIError(*collision.as_tuple()[:3])
    return canonical
