"""Strict ownership topology for worksheet X14 conditional formatting."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile
import zlib

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology

_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_X14: Final = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
_XM: Final = "http://schemas.microsoft.com/office/excel/2006/main"
_WORKSHEET: Final = f"{{{_SML}}}worksheet"
_EXTLST: Final = f"{{{_SML}}}extLst"
_EXT: Final = f"{{{_SML}}}ext"
_FORMATTINGS: Final = f"{{{_X14}}}conditionalFormattings"
_FORMATTING: Final = f"{{{_X14}}}conditionalFormatting"
_RULE: Final = f"{{{_X14}}}cfRule"
_DXF: Final = f"{{{_X14}}}dxf"
_F: Final = f"{{{_XM}}}f"
_SQREF: Final = f"{{{_XM}}}sqref"
_DV: Final = f"{{{_X14}}}dataValidations"
_CF_URI: Final = "{78C0D931-6437-407d-A8EE-F0AAD7539E65}"
_DV_URI: Final = "{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"
_OWNED = frozenset({_FORMATTINGS, _FORMATTING, _RULE, _DXF, _F, _SQREF})
_OWNED_LOCALS = frozenset({"conditionalFormattings", "conditionalFormatting", "cfRule", "dxf", "f", "sqref"})

__all__ = (
    "OPCWorksheetX14CfOwnerTopologyError", "X14CfContainerOwner",
    "WorksheetX14CfOwnerTopology", "WorkbookX14CfOwnerTopology",
    "read_worksheet_x14_cf_owner_topology",
)


@dataclass(frozen=True)
class X14CfContainerOwner:
    owner_path: str
    document_order: int


@dataclass(frozen=True)
class WorksheetX14CfOwnerTopology:
    worksheet: WorksheetDescriptor
    containers: tuple[X14CfContainerOwner, ...]


@dataclass(frozen=True)
class WorkbookX14CfOwnerTopology:
    worksheets: tuple[WorksheetX14CfOwnerTopology, ...]


@dataclass
class OPCWorksheetX14CfOwnerTopologyError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetX14CfOwnerTopologyError(code, subject, field, detail)


def _path(value: os.PathLike[str] | str) -> str:
    subject = f"{type(value).__module__}.{type(value).__qualname__}"
    try:
        result = os.fspath(value)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except Exception as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(result, str):
        _fail("invalid-package-path", subject, "path", type(result).__name__)
    if "\x00" in result:
        _fail("unreadable-package", result, "path", "embedded-nul")
    return result


def _case_dot_key(value: str) -> str | None:
    if not value or value.startswith("/") or value.endswith("/") or "//" in value:
        return None
    parts: list[str] = []
    for item in value.split("/"):
        if item == ".":
            continue
        if item == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(item)
    return "/".join(parts).casefold()


def _member(path: str, part: CanonicalPartURI) -> bytes:
    try:
        with ZipFile(path) as archive:
            matches = []
            for info in archive.infolist():
                try:
                    canonical = canonicalize_part_uri(info.filename)
                except OPCPartURIError:
                    if _case_dot_key(info.filename) != part.value.casefold():
                        _fail("unreadable-worksheet-part", part.value, "member", "invalid-member-name")
                    matches.append(info)
                    continue
                if canonical == part or canonical.value.casefold() == part.value.casefold() or _case_dot_key(info.filename) == part.value.casefold():
                    matches.append(info)
            if not matches:
                _fail("missing-worksheet-member", part.value, "member", part.value)
            if len(matches) != 1:
                _fail("ambiguous-worksheet-member", part.value, "member", part.value)
            if matches[0].filename != part.value:
                _fail("noncanonical-worksheet-member", part.value, "member", matches[0].filename)
            return archive.read(matches[0])
    except OPCWorksheetX14CfOwnerTopologyError:
        raise
    except (BadZipFile, LargeZipFile, KeyError, OSError, RuntimeError, ValueError, zlib.error) as error:
        _fail("unreadable-worksheet-part", part.value, "xml", type(error).__name__)
    raise AssertionError("unreachable")


def _xml(payload: bytes, part: CanonicalPartURI) -> ET.Element:
    try:
        return ET.fromstring(payload)
    except (LookupError, ValueError):
        _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
    except ET.ParseError as error:
        if "unknown encoding" in str(error).lower():
            _fail("unsupported-xml-encoding", part.value, "xml", "encoding")
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")
    except UnicodeError:
        _fail("malformed-worksheet-xml", part.value, "xml", "xml")


def _local(value: object) -> str:
    return value.rsplit("}", 1)[-1] if isinstance(value, str) else ""


def _nonwhite(value: str | None) -> bool:
    return bool(value and not value.isspace())


def _record(faults: list[tuple[int, int, tuple[str, str, str, str]]], tier: int, order: int, error: tuple[str, str, str, str]) -> None:
    faults.append((tier, order, error))


def _is_dv_carve(element: ET.Element, parent: ET.Element | None, grandparent: ET.Element | None, great: ET.Element | None) -> bool:
    return (element.tag in {_F, _SQREF} and parent is not None and parent.tag == _DV and grandparent is not None
            and grandparent.tag == _EXT and grandparent.attrib == {"uri": _DV_URI} and great is not None and great.tag == _EXTLST)


def _validate(root: ET.Element, part: CanonicalPartURI) -> tuple[X14CfContainerOwner, ...]:
    """Run one preorder ownership pass, retaining only valid owner boundaries."""
    faults: list[tuple[int, int, tuple[str, str, str, str]]] = []
    parents: dict[ET.Element, ET.Element | None] = {root: None}
    order = 0
    cf_exts: list[ET.Element] = []
    containers: list[ET.Element] = []
    for parent in root.iter():
        for child in parent:
            parents[child] = parent
    for element in root.iter():
        order += 1
        parent = parents[element]
        grand = parents.get(parent) if parent is not None else None
        great = parents.get(grand) if grand is not None else None
        tag = element.tag
        local = _local(tag)
        # Namespace collisions are evaluated before generic placement, except native SML counterparts.
        if local in _OWNED_LOCALS and tag not in _OWNED:
            if tag not in {f"{{{_SML}}}conditionalFormatting", f"{{{_SML}}}cfRule", f"{{{_SML}}}f"}:
                _record(faults, 1, order, ("x14-cf-namespace-collision", part.value, "tag", str(tag)))
            continue
        if tag == _FORMATTINGS:
            if parent is None or parent.tag != _EXT or parent.attrib.get("uri") != _CF_URI:
                _record(faults, 1, order, ("invalid-x14-cf-parent", part.value, "tag", str(tag)))
            else:
                cf_exts.append(parent)
        elif tag == _FORMATTING:
            if parent is None or parent.tag != _FORMATTINGS:
                _record(faults, 1, order, ("invalid-x14-cf-parent", part.value, "tag", str(tag)))
            else:
                containers.append(element)
        elif tag == _RULE:
            if parent is None or parent.tag != _FORMATTING:
                _record(faults, 1, order, ("invalid-x14-cf-parent", part.value, "tag", str(tag)))
        elif tag == _DXF:
            if parent is None or parent.tag != _RULE:
                _record(faults, 1, order, ("invalid-x14-cf-parent", part.value, "tag", str(tag)))
        elif tag == _F:
            if (parent is None or parent.tag != _RULE) and not _is_dv_carve(element, parent, grand, great):
                _record(faults, 1, order, ("invalid-x14-cf-parent", part.value, "tag", str(tag)))
        elif tag == _SQREF:
            if parent is None or parent.tag != _FORMATTING:
                if not _is_dv_carve(element, parent, grand, great):
                    _record(faults, 1, order, ("invalid-x14-cf-parent", part.value, "tag", str(tag)))
        if element.tag == _EXT and parent is not None and parent.tag == _EXTLST and any(child.tag == _FORMATTINGS for child in element):
            uri = element.attrib.get("uri", "")
            if uri != _CF_URI:
                _record(faults, 1, order, ("unsupported-x14-cf-extension-uri", part.value, "uri", uri))
    direct_extlsts = [child for child in root if child.tag == _EXTLST]
    for extlst in direct_extlsts:
        if extlst.attrib:
            _record(faults, 2, 1, ("unknown-x14-cf-attribute", part.value, "attribute", sorted(extlst.attrib)[0]))
        if _nonwhite(extlst.text):
            _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "extLst", "text"))
        for ext in extlst:
            if _nonwhite(ext.tail): _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "extLst", "tail"))
            if ext.tag != _EXT or ext.attrib.get("uri") != _CF_URI: continue
            if set(ext.attrib) != {"uri"}:
                bad = sorted(set(ext.attrib) - {"uri"})[0] if set(ext.attrib) - {"uri"} else "uri"
                _record(faults, 2, 1, ("unknown-x14-cf-attribute", part.value, "attribute", bad))
            forms = [child for child in ext if child.tag == _FORMATTINGS]
            if len(forms) != 1:
                _record(faults, 1, 1, ("invalid-x14-cf-cardinality", part.value, "ext", "conditionalFormattings"))
            if _nonwhite(ext.text): _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "ext", "text"))
            for child in ext:
                if child.tag != _FORMATTINGS: _record(faults, 2, 1, ("unknown-x14-cf-child", part.value, "tag", str(child.tag)))
                if _nonwhite(child.tail): _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "ext", "tail"))
    if len(cf_exts) > 1:
        _record(faults, 1, 1, ("duplicate-x14-cf-extension", part.value, "uri", _CF_URI))
    for forms in {element for element in cf_exts for element in element if element.tag == _FORMATTINGS}:
        if forms.attrib: _record(faults, 2, 1, ("unknown-x14-cf-attribute", part.value, "attribute", sorted(forms.attrib)[0]))
        if not any(child.tag == _FORMATTING for child in forms): _record(faults, 1, 1, ("invalid-x14-cf-cardinality", part.value, "conditionalFormattings", "conditionalFormatting"))
        if _nonwhite(forms.text): _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "conditionalFormattings", "text"))
        for child in forms:
            if child.tag != _FORMATTING: _record(faults, 2, 1, ("unknown-x14-cf-child", part.value, "tag", str(child.tag)))
            if _nonwhite(child.tail): _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "conditionalFormattings", "tail"))
    for container in containers:
        if container.attrib: _record(faults, 2, 1, ("unknown-x14-cf-attribute", part.value, "attribute", sorted(container.attrib)[0]))
        if _nonwhite(container.text): _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "conditionalFormatting", "text"))
        for child in container:
            if child.tag not in {_RULE, _SQREF}: _record(faults, 2, 1, ("unknown-x14-cf-child", part.value, "tag", str(child.tag)))
            if _nonwhite(child.tail): _record(faults, 2, 1, ("invalid-x14-cf-content", part.value, "conditionalFormatting", "tail"))
            if child.tag == _RULE:
                for grandchild in child:
                    if grandchild.tag not in {_F, _DXF}:
                        _record(faults, 2, 1, ("unknown-x14-cf-child", part.value, "tag", str(grandchild.tag)))
    if faults:
        tier = min(tier for tier, _, _ in faults)
        _, _, selected = min((item for item in faults if item[0] == tier), key=lambda item: item[1])
        _fail(*selected)
    owners = []
    for number, container in enumerate(containers, start=1):
        forms = parents[container]; ext = parents[forms]; extlst = parents[ext]
        container_index = [item for item in forms if item.tag == _FORMATTING].index(container) + 1
        ext_index = [item for item in extlst if item.tag == _EXT].index(ext) + 1
        extlst_index = [item for item in root if item.tag == _EXTLST].index(extlst) + 1
        owners.append(X14CfContainerOwner(f"{part.value}/worksheet/extLst[{extlst_index}]/ext[{ext_index}]/conditionalFormattings[1]/conditionalFormatting[{container_index}]", number))
    return tuple(owners)


def read_worksheet_x14_cf_owner_topology(package_path: os.PathLike[str] | str) -> WorkbookX14CfOwnerTopology:
    """Return immutable X14 CF owner paths after validating every worksheet."""
    path = _path(package_path)
    topology = read_workbook_topology(path)
    trees = [(worksheet, worksheet.worksheet_part, _xml(_member(path, worksheet.worksheet_part), worksheet.worksheet_part)) for worksheet in topology.worksheets]
    for _, part, root in trees:
        if root.tag != _WORKSHEET:
            _fail("invalid-worksheet-root", part.value, "root", str(root.tag))
    records = [(worksheet, _validate(root, part)) for worksheet, part, root in trees]
    return WorkbookX14CfOwnerTopology(tuple(WorksheetX14CfOwnerTopology(worksheet, containers) for worksheet, containers in records))
