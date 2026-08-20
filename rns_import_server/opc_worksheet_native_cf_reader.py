"""Strict, immutable native SpreadsheetML conditional-formatting presence."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology


_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_X14: Final = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
_WORKSHEET: Final = f"{{{_SML}}}worksheet"
_CONTAINER: Final = f"{{{_SML}}}conditionalFormatting"
_RULE: Final = f"{{{_SML}}}cfRule"
_X14_LOCALS: Final = frozenset({"conditionalFormattings", "conditionalFormatting", "cfRule"})
_OWNED_LOCALS: Final = frozenset({"conditionalFormatting", "cfRule"})

__all__ = (
    "OPCWorksheetNativeCfReaderError",
    "WorkbookNativeCfPresence",
    "WorksheetNativeCfPresence",
    "read_worksheet_native_cf_presence",
)


@dataclass(frozen=True)
class WorksheetNativeCfPresence:
    worksheet: WorksheetDescriptor
    has_native_conditional_formatting: bool


@dataclass(frozen=True)
class WorkbookNativeCfPresence:
    worksheets: tuple[WorksheetNativeCfPresence, ...]


@dataclass
class OPCWorksheetNativeCfReaderError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetNativeCfReaderError(code, subject, field, detail)


def _coerce_package_path(value: os.PathLike[str] | str) -> str:
    subject = f"{type(value).__module__}.{type(value).__qualname__}"
    try:
        path = os.fspath(value)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except (ValueError, OSError) as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str):
        _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path:
        _fail("unreadable-package", path, "path", "embedded-nul")
    return path


def _member(path: str, part: CanonicalPartURI) -> bytes:
    """Read exactly one raw canonical ZIP member owned by topology."""
    try:
        with ZipFile(path) as archive:
            matches = []
            for info in archive.infolist():
                try:
                    canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError:
                    _fail("unreadable-worksheet-part", part.value, "member", "invalid-member-name")
                if canonical == part:
                    matches.append(info)
            if not matches:
                _fail("missing-worksheet-member", part.value, "member", part.value)
            if len(matches) != 1:
                _fail("ambiguous-worksheet-member", part.value, "member", part.value)
            info = matches[0]
            if info.filename != part.value:
                _fail("noncanonical-worksheet-member", part.value, "member", info.filename)
            return archive.read(info)
    except OPCWorksheetNativeCfReaderError:
        raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError) as error:
        _fail("unreadable-worksheet-part", part.value, "xml", type(error).__name__)
    raise AssertionError("unreachable")


def _xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    try:
        root = ET.fromstring(payload)
    except LookupError:
        _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except (ET.ParseError, UnicodeError, ValueError):
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    if root.tag != _WORKSHEET:
        _fail("invalid-worksheet-root", part.value, "root", str(root.tag))
    return root


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _x14_hard_stop(root: ET.Element, part: CanonicalPartURI) -> None:
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith(f"{{{_X14}}}") and _local(element.tag) in _X14_LOCALS:
            _fail("unsupported_x14_content", part.value, "tag", element.tag)


def _nonwhite(value: str | None) -> bool:
    return bool(value and not value.isspace())


def _owned_mixed(element: ET.Element, part: CanonicalPartURI) -> None:
    name = _local(element.tag)
    if _nonwhite(element.text):
        _fail("invalid-native-cf-content", part.value, name, "text")
    for child in element:
        if _nonwhite(child.tail):
            _fail("invalid-native-cf-content", part.value, name, "tail")


def _validate_owned_placement(root: ET.Element, part: CanonicalPartURI) -> None:
    """Validate only placement and namespace of CF tags this reader owns."""
    for parent in root.iter():
        parent_is_root = parent is root
        parent_is_container = parent.tag == _CONTAINER and parent in tuple(root)
        for child in parent:
            local = _local(child.tag)
            if child.tag in {_CONTAINER, _RULE}:
                valid = (child.tag == _CONTAINER and parent_is_root) or (
                    child.tag == _RULE and parent_is_container
                )
                if not valid:
                    _fail("invalid-owned-native-cf-parent", part.value, "tag", str(child.tag))
                continue
            if local not in _OWNED_LOCALS:
                continue
            if parent_is_root or parent_is_container:
                _fail("owned-native-cf-namespace-collision", part.value, "tag", str(child.tag))

    for container in root:
        if container.tag == _CONTAINER:
            _owned_mixed(container, part)
            for rule in container:
                if rule.tag == _RULE:
                    _owned_mixed(rule, part)


def _presence(root: ET.Element) -> bool:
    return any(child.tag == _CONTAINER for child in root)


def read_worksheet_native_cf_presence(package_path: os.PathLike[str] | str) -> WorkbookNativeCfPresence:
    """Inventory native CF container presence; never parse semantic CF content."""
    path = _coerce_package_path(package_path)
    topology = read_workbook_topology(path)
    records = []
    for worksheet in topology.worksheets:
        part = worksheet.worksheet_part
        root = _xml(_member(path, part), part)
        _x14_hard_stop(root, part)
        _validate_owned_placement(root, part)
        records.append(WorksheetNativeCfPresence(worksheet, _presence(root)))
    return WorkbookNativeCfPresence(tuple(records))
