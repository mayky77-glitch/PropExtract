"""Strict, immutable envelope reader for worksheet-owned X14 conditional formats."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Final, Iterator
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile
import zlib

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology


_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_X14: Final = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
_XM: Final = "http://schemas.microsoft.com/office/excel/2006/main"
_URI: Final = "{78C0D931-6437-407d-A8EE-F0AAD7539E65}"
_WORKSHEET: Final = f"{{{_SML}}}worksheet"
_EXT_LIST: Final = f"{{{_SML}}}extLst"
_EXT: Final = f"{{{_SML}}}ext"
_FORMATTINGS: Final = f"{{{_X14}}}conditionalFormattings"
_CONTAINER: Final = f"{{{_X14}}}conditionalFormatting"
_RULE: Final = f"{{{_X14}}}cfRule"
_FORMULA: Final = f"{{{_XM}}}f"
_SQREF: Final = f"{{{_XM}}}sqref"
_DXF: Final = f"{{{_X14}}}dxf"
_FONT: Final = f"{{{_SML}}}font"
_FILL: Final = f"{{{_SML}}}fill"
_OWNED_TAGS: Final = frozenset({_FORMATTINGS, _CONTAINER, _RULE, _DXF})
_OWNED_LOCALS: Final = frozenset({"conditionalFormattings", "conditionalFormatting", "cfRule", "dxf", "f", "sqref"})
_XML_WHITE: Final = frozenset({" ", "\t", "\r", "\n"})
_BOOL: Final = {"0": False, "1": True, "false": False, "true": True}
_MAX_INT32: Final = 2_147_483_647

__all__ = (
    "OPCWorksheetX14CfReaderError", "WorkbookX14CfEnvelope", "WorksheetX14CfEnvelope",
    "X14CfContainerEnvelope", "X14CfRuleEnvelope", "read_worksheet_x14_cf_envelope",
)


@dataclass(frozen=True)
class X14CfRuleEnvelope:
    owner_path: str
    document_order: int
    type: str
    priority: int
    stop_if_true: bool
    rule_id: str
    formula: str
    has_inline_dxf: bool


@dataclass(frozen=True)
class X14CfContainerEnvelope:
    owner_path: str
    sqref_text: str
    rules: tuple[X14CfRuleEnvelope, ...]


@dataclass(frozen=True)
class WorksheetX14CfEnvelope:
    worksheet: WorksheetDescriptor
    containers: tuple[X14CfContainerEnvelope, ...]


@dataclass(frozen=True)
class WorkbookX14CfEnvelope:
    worksheets: tuple[WorksheetX14CfEnvelope, ...]


@dataclass
class OPCWorksheetX14CfReaderError(ValueError):
    code: str
    subject: str
    field: str
    detail: str

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.code, self.subject, self.field, self.detail)

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.code, self.subject, self.field, self.detail)


def _fail(code: str, subject: str, field: str, detail: str) -> None:
    raise OPCWorksheetX14CfReaderError(code, subject, field, detail)


def _path(value: os.PathLike[str] | str) -> str:
    subject = f"{type(value).__module__}.{type(value).__qualname__}"
    try:
        path = os.fspath(value)
    except TypeError as error:
        _fail("invalid-package-path", subject, "path", type(error).__name__)
    except Exception as error:
        _fail("unreadable-package", subject, "path", type(error).__name__)
    if not isinstance(path, str):
        _fail("invalid-package-path", subject, "path", type(path).__name__)
    if "\x00" in path:
        _fail("unreadable-package", path, "path", "embedded-nul")
    return path


def _case_dot_key(value: str) -> str | None:
    if not value or value.startswith("/") or value.endswith("/") or "//" in value:
        return None
    result: list[str] = []
    for segment in value.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if not result:
                return None
            result.pop()
        else:
            result.append(segment)
    return "/".join(result).casefold()


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
    except OPCWorksheetX14CfReaderError:
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


def _trees(package_path: os.PathLike[str] | str) -> Iterator[tuple[WorksheetDescriptor, CanonicalPartURI, ET.Element]]:
    path = _path(package_path)
    topology = read_workbook_topology(path)
    for worksheet in topology.worksheets:
        part = worksheet.worksheet_part
        yield worksheet, part, _xml(_member(path, part), part)


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _nonwhite(value: str | None) -> bool:
    return bool(value and not value.isspace())


def _mixed(element: ET.Element, part: CanonicalPartURI, field: str) -> None:
    if _nonwhite(element.text):
        _fail("invalid-x14-cf-content", part.value, field, "text")
    for child in element:
        if _nonwhite(child.tail):
            _fail("invalid-x14-cf-content", part.value, field, "tail")


def _owned_child_collision(element: ET.Element, part: CanonicalPartURI,
                           legal: frozenset[str]) -> None:
    """Reject only local-name impostors in a recognized CF owner subtree."""
    for child in element:
        if _local(child.tag) in _OWNED_LOCALS and child.tag not in legal:
            _fail("x14-cf-namespace-collision", part.value, "tag", str(child.tag))


def _parent_chain(root: ET.Element, part: CanonicalPartURI) -> tuple[tuple[ET.Element, ET.Element, int], ...]:
    """Find owned formatters with the deliberately narrow, ordered ownership walk.

    The worksheet can carry other X14 extensions (notably the data-validation
    extension).  A whole-tree local-name search would accidentally make those
    foreign payloads ours.  Only the worksheet/extLst/ext ownership depths are
    therefore collision-sensitive.
    """
    if root.tag != _WORKSHEET:
        _fail("invalid-worksheet-root", part.value, "root", str(root.tag))
    found: list[tuple[ET.Element, ET.Element, int]] = []
    for worksheet_child in root:
        if _local(worksheet_child.tag) == "conditionalFormattings":
            if worksheet_child.tag == _FORMATTINGS:
                _fail("invalid-x14-cf-parent", part.value, "tag", str(worksheet_child.tag))
            _fail("x14-cf-namespace-collision", part.value, "tag", str(worksheet_child.tag))
        if worksheet_child.tag != _EXT_LIST:
            continue
        for ext_index, ext in enumerate(worksheet_child, start=1):
            if _local(ext.tag) == "conditionalFormattings":
                if ext.tag == _FORMATTINGS:
                    _fail("invalid-x14-cf-parent", part.value, "tag", str(ext.tag))
                _fail("x14-cf-namespace-collision", part.value, "tag", str(ext.tag))
            if ext.tag != _EXT:
                continue
            for formatting in ext:
                if _local(formatting.tag) != "conditionalFormattings":
                    continue
                if formatting.tag != _FORMATTINGS:
                    _fail("x14-cf-namespace-collision", part.value, "tag", str(formatting.tag))
                if ext.attrib.get("uri") != _URI:
                    _fail("unsupported-x14-cf-extension-uri", part.value, "uri", ext.attrib.get("uri", ""))
                _owned_child_collision(formatting, part, frozenset({_CONTAINER}))
                for container in formatting:
                    if container.tag != _CONTAINER:
                        continue
                    _owned_child_collision(container, part, frozenset({_RULE, _SQREF}))
                    for rule in container:
                        if rule.tag == _RULE:
                            _owned_child_collision(rule, part, frozenset({_FORMULA, _DXF}))
                found.append((ext, formatting, ext_index))
    return tuple(found)


def _attributes(element: ET.Element, part: CanonicalPartURI, allowed: frozenset[str], *, rule: bool = False) -> None:
    unknown = sorted(set(element.attrib) - allowed)
    if unknown:
        _fail("unknown-x14-cf-attribute", part.value, "attribute", unknown[0])
    if rule and set(element.attrib) != allowed:
        missing = sorted(allowed - set(element.attrib))
        _fail("invalid-x14-cf-content", part.value, "attribute", missing[0])


def _integer(value: str, part: CanonicalPartURI) -> int:
    words: list[str] = []
    word: list[str] = []
    for character in value:
        if character in _XML_WHITE:
            if word:
                words.append("".join(word))
                word.clear()
        else:
            word.append(character)
    if word:
        words.append("".join(word))
    collapsed = " ".join(words)
    sign = -1 if collapsed.startswith("-") else 1
    digits = collapsed[1:] if collapsed.startswith(("+", "-")) else collapsed
    if not digits or not digits.isascii() or not digits.isdecimal():
        _fail("invalid-x14-cf-priority", part.value, "priority", value)
    significant = digits.lstrip("0") or "0"
    maximum = str(_MAX_INT32)
    if (len(significant) > len(maximum) or (len(significant) == len(maximum) and significant > maximum)
            or sign < 0 or significant == "0"):
        _fail("invalid-x14-cf-priority", part.value, "priority", value)
    return int(significant)


def _text(element: ET.Element, part: CanonicalPartURI, field: str, code: str) -> str:
    _attributes(element, part, frozenset())
    if list(element):
        _fail(code, part.value, field, "nested")
    text = element.text
    if text is None or text.isspace():
        _fail(code, part.value, field, "blank")
    return text


def _dxf(element: ET.Element, part: CanonicalPartURI) -> None:
    _attributes(element, part, frozenset())
    _mixed(element, part, "dxf")
    for child in element:
        if child.tag not in {_FONT, _FILL}:
            _fail("unknown-x14-cf-child", part.value, "tag", str(child.tag))


def _owner(part: CanonicalPartURI, ext_index: int, formatting_index: int, container_index: int) -> str:
    return (f"{part.value}/worksheet/extLst/ext[{ext_index}]/conditionalFormattings[{formatting_index}]"
            f"/conditionalFormatting[{container_index}]")


def _container(element: ET.Element, part: CanonicalPartURI, owner: str, order: int, priorities: set[int]) -> tuple[X14CfContainerEnvelope, int]:
    _attributes(element, part, frozenset())
    _mixed(element, part, "conditionalFormatting")
    children = list(element)
    rules = [child for child in children if child.tag == _RULE]
    sqrefs = [child for child in children if child.tag == _SQREF]
    if any(child.tag not in {_RULE, _SQREF} for child in children):
        _fail("unknown-x14-cf-child", part.value, "tag", str(next(child.tag for child in children if child.tag not in {_RULE, _SQREF})))
    if len(sqrefs) != 1 or not rules:
        _fail("invalid-x14-cf-cardinality", part.value, "conditionalFormatting", "sqref" if len(sqrefs) != 1 else "cfRule")
    if children != rules + sqrefs:
        _fail("invalid-x14-cf-order", part.value, "conditionalFormatting", "cfRule/sqref")
    sqref = _text(sqrefs[0], part, "sqref", "invalid-x14-cf-sqref")
    records = []
    for index, rule in enumerate(rules, start=1):
        _attributes(rule, part, frozenset({"type", "priority", "stopIfTrue", "id"}), rule=True)
        _mixed(rule, part, "cfRule")
        rule_type = rule.attrib["type"]
        if rule_type != "expression":
            _fail("unsupported-x14-cf-rule-type", part.value, "type", rule_type)
        priority = _integer(rule.attrib["priority"], part)
        if priority in priorities:
            _fail("duplicate-x14-cf-priority", part.value, "priority", rule.attrib["priority"])
        if rule.attrib["stopIfTrue"] not in _BOOL:
            _fail("invalid-x14-cf-boolean", part.value, "stopIfTrue", rule.attrib["stopIfTrue"])
        if not rule.attrib["id"].strip():
            _fail("invalid-x14-cf-id", part.value, "id", rule.attrib["id"])
        rule_children = list(rule)
        if len(rule_children) != 2:
            _fail("invalid-x14-cf-cardinality", part.value, "cfRule", "f/dxf")
        if rule_children[0].tag != _FORMULA or rule_children[1].tag != _DXF:
            _fail("invalid-x14-cf-order", part.value, "cfRule", "f/dxf")
        formula = _text(rule_children[0], part, "formula", "invalid-x14-cf-formula")
        _dxf(rule_children[1], part)
        order += 1
        priorities.add(priority)
        records.append(X14CfRuleEnvelope(f"{owner}/cfRule[{index}]", order, rule_type, priority,
                                         _BOOL[rule.attrib["stopIfTrue"]], rule.attrib["id"], formula, True))
    return X14CfContainerEnvelope(owner, sqref, tuple(records)), order


def _worksheet(root: ET.Element, part: CanonicalPartURI) -> tuple[X14CfContainerEnvelope, ...]:
    found = _parent_chain(root, part)
    priorities: set[int] = set()
    order = 0
    containers: list[X14CfContainerEnvelope] = []
    found_by_ext = {ext: formattings for ext, formattings, _ in found}
    for ext_list in root:
        if ext_list.tag != _EXT_LIST:
            continue
        for ext_index, ext in enumerate(ext_list, start=1):
            if ext.tag != _EXT or ext.attrib.get("uri") != _URI:
                continue
            _attributes(ext_list, part, frozenset())
            _mixed(ext_list, part, "extLst")
            _attributes(ext, part, frozenset({"uri"}), rule=True)
            _mixed(ext, part, "ext")
            formattings = [child for child in ext if child.tag == _FORMATTINGS]
            if any(child.tag != _FORMATTINGS for child in ext):
                _fail("unknown-x14-cf-child", part.value, "tag", str(next(child.tag for child in ext if child.tag != _FORMATTINGS)))
            if len(formattings) != 1:
                _fail("invalid-x14-cf-cardinality", part.value, "ext", "conditionalFormattings")
            formatting = formattings[0]
            if found_by_ext.get(ext) is not formatting:
                raise AssertionError("validated X14 CF extension missing from ancestry walk")
            formatting_index = 1
            _attributes(formatting, part, frozenset())
            _mixed(formatting, part, "conditionalFormattings")
            if not list(formatting):
                _fail("invalid-x14-cf-cardinality", part.value, "conditionalFormattings", "conditionalFormatting")
            for container_index, container in enumerate(formatting, start=1):
                if container.tag != _CONTAINER:
                    _fail("unknown-x14-cf-child", part.value, "tag", str(container.tag))
                record, order = _container(
                    container, part, _owner(part, ext_index, formatting_index, container_index), order, priorities,
                )
                containers.append(record)
    return tuple(containers)


def read_worksheet_x14_cf_envelope(package_path: os.PathLike[str] | str) -> WorkbookX14CfEnvelope:
    """Read only the frozen X14 CF ownership envelope for topology worksheets."""
    records = []
    for worksheet, part, root in _trees(package_path):
        records.append(WorksheetX14CfEnvelope(worksheet, _worksheet(root, part)))
    return WorkbookX14CfEnvelope(tuple(records))
