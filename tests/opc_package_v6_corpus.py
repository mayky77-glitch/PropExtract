"""Direct deterministic ZIP/XML oracle; no production imports."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote_to_bytes
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "opc-package-v6"
CONTENT_TYPES_INPUT = FIXTURE_ROOT / "content-types.xml"
VALID_WORKBOOK_RELS_INPUT = FIXTURE_ROOT / "valid-workbook.rels.xml"
Mutation = tuple[str, str, str, str]
_REL_TAG, _CHILD = f"{{{REL_NS}}}Relationships", f"{{{REL_NS}}}Relationship"
_TIME, _TYPE = (1980, 1, 1, 0, 0, 0), "http://example.test/worksheet"

@dataclass(frozen=True)
class PackageFixture:
    name: str; members: tuple[tuple[str, bytes], ...]; expected_mutations: tuple[Mutation, ...]
    @property
    def manifest(self) -> tuple[str, ...]: return tuple(name for name, _ in self.members)

def _rels(*rows: tuple[str, str, str, str], namespace: str = REL_NS) -> bytes:
    body = "".join('<Relationship Id="%s" Type="%s" Target="%s"%s/>' % (i, t, x, "" if m == "Internal" else f' TargetMode="{m}"') for i, t, x, m in rows)
    return f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{namespace}">{body}</Relationships>'.encode()

def _members(rels: bytes, *, rels_name: str = "xl/_rels/workbook.xml.rels", extras: tuple[tuple[str, bytes], ...] = ()) -> tuple[tuple[str, bytes], ...]:
    return (("[Content_Types].xml", CONTENT_TYPES_INPUT.read_bytes()), ("_rels/.rels", _rels(("rRoot", "http://example.test/officeDocument", "xl/workbook.xml", "Internal"))), ("xl/workbook.xml", b'<workbook xmlns="urn:fixture:spreadsheet"/>'), (rels_name, rels), ("xl/worksheets/sheet1.xml", b'<worksheet xmlns="urn:fixture:spreadsheet"/>'), *extras)

_VALID = VALID_WORKBOOK_RELS_INPUT.read_bytes()
FIXTURES = (
    PackageFixture("valid", _members(_VALID), ()),
    PackageFixture("invalid-part", _members(_VALID, extras=(("xl/../bad.xml", b'<part xmlns="urn:fixture"/>'),)), (("invalid-part-uri", "xl/../bad.xml", "name", "invalid-part-segment"),)),
    PackageFixture("invalid-target", _members(_rels(("rSheet", _TYPE, "worksheets/%2Fsheet1.xml", "Internal"))), (("invalid-relationship-target", "xl/workbook.xml", "Target", "worksheets/%2Fsheet1.xml"),)),
    PackageFixture("invalid-type", _members(_rels(("rSheet", "not an absolute URI", "worksheets/sheet1.xml", "Internal"))), (("invalid-relationship-type", "xl/workbook.xml", "Type", "not an absolute URI"),)),
    PackageFixture("invalid-id", _members(_rels(("1bad", _TYPE, "worksheets/sheet1.xml", "Internal"))), (("invalid-relationship-id", "xl/workbook.xml", "Id", "1bad"),)),
    PackageFixture("invalid-source", _members(_VALID, rels_name="xl/_rels/../workbook.xml.rels"), (("invalid-relationship-source", "xl/_rels/../workbook.xml.rels", "source", "xl/../workbook.xml"),)),
    PackageFixture("invalid-mode", _members(_rels(("rSheet", _TYPE, "worksheets/sheet1.xml", "Remote"))), (("invalid-target-mode", "xl/workbook.xml", "TargetMode", "Remote"),)),
    PackageFixture("invalid-namespace", _members(_rels(("rSheet", _TYPE, "worksheets/sheet1.xml", "Internal"), namespace="urn:wrong-rels")), (("invalid-relationships-namespace", "xl/_rels/workbook.xml.rels", "namespace", "urn:wrong-rels"),)),
    PackageFixture("percent-alias", _members(_rels(("rSheet", _TYPE, "worksheets/%73heet1.xml", "Internal"))), ()),
    PackageFixture("unicode", _members(_rels(("лист", _TYPE, "worksheets/лист.xml", "Internal")), extras=(("xl/worksheets/лист.xml", b'<worksheet xmlns="urn:fixture:spreadsheet"/>'),)), ()),
    PackageFixture("controls", _members(_rels(("rSheet", _TYPE, "worksheets/%00sheet1.xml", "Internal"))), (("invalid-relationship-target", "xl/workbook.xml", "Target", "worksheets/%00sheet1.xml"),)),
    PackageFixture("encoded-traversal", _members(_rels(("rSheet", _TYPE, "worksheets/%2E%2E/sheet1.xml", "Internal"))), (("invalid-relationship-target", "xl/workbook.xml", "Target", "worksheets/%2E%2E/sheet1.xml"),)),
    PackageFixture("ordered-multiple-errors", _members(_rels(("1bad", "not an absolute URI", "worksheets/%00sheet1.xml", "Internal"), ("rSecond", _TYPE, "worksheets/missing.xml", "Internal"), ("rThird", _TYPE, "worksheets/sheet1.xml", "Remote"))), (("invalid-relationship-id", "xl/workbook.xml", "Id", "1bad"), ("invalid-relationship-type", "xl/workbook.xml", "Type", "not an absolute URI"), ("invalid-relationship-target", "xl/workbook.xml", "Target", "worksheets/%00sheet1.xml"), ("missing-internal-target", "xl/workbook.xml", "Target", "worksheets/missing.xml"), ("invalid-target-mode", "xl/workbook.xml", "TargetMode", "Remote"))),
)

def _info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=_TIME); info.create_system = 3; info.external_attr = 0o100644 << 16; info.compress_type = ZIP_DEFLATED
    return info
def write_fixture(destination: Path, fixture: PackageFixture) -> Path:
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as z:
        for name, payload in fixture.members: z.writestr(_info(name), payload, compress_type=ZIP_DEFLATED, compresslevel=9)
    return destination
def fixture_hash(path: Path) -> str: return sha256(path.read_bytes()).hexdigest()
def package_structure(path: Path) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    with ZipFile(path) as z:
        names = tuple(z.namelist()); roots = tuple((n, ET.fromstring(z.read(n)).tag) for n in names if n.endswith(".xml") or n.endswith(".rels"))
    return names, roots

def _part(value: str) -> str | None:
    if not value or value.startswith("/") or value.endswith("/") or "//" in value or any(c in value for c in "\\?#"): return None
    try: decoded = unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError: return None
    if any(ord(c) <= 31 or ord(c) == 127 or 128 <= ord(c) <= 159 for c in decoded) or any(s in {"", ".", ".."} for s in decoded.split("/")): return None
    return decoded
def _resolve(source: str | None, target: str) -> str | None:
    if not target or target.startswith("/") or any(c in target for c in "\\?#"): return None
    try: decoded = unquote_to_bytes(target).decode("utf-8")
    except UnicodeDecodeError: return None
    if any(ord(c) <= 31 or ord(c) == 127 or 128 <= ord(c) <= 159 for c in decoded) or "%2f" in target.lower() or "%2e" in target.lower(): return None
    stack = [] if source is None else source.split("/")[:-1]
    for segment in decoded.split("/"):
        if segment in {"", "."}: continue
        if segment == "..":
            if not stack: return None
            stack.pop()
        else: stack.append(segment)
    return _part("/".join(stack))
def _source(name: str) -> str | None:
    if name == "_rels/.rels": return None
    if "/_rels/" not in name or not name.endswith(".rels"): return ""
    prefix, suffix = name.split("/_rels/", 1); return f"{prefix}/{suffix.removesuffix('.rels')}"

def mutation_tuples(path: Path) -> tuple[Mutation, ...]:
    """Findings derive only from ZIP/XML bytes, in archive/XML order."""
    with ZipFile(path) as z: names, payloads = tuple(z.namelist()), {n: z.read(n) for n in z.namelist()}
    out: list[Mutation] = []; parts: set[str] = set()
    for name in names:
        if name == "[Content_Types].xml" or name.endswith(".rels"): continue
        canonical = _part(name)
        if canonical is None: out.append(("invalid-part-uri", name, "name", "invalid-part-segment"))
        else: parts.add(canonical)
    for name in names:
        if not name.endswith(".rels"): continue
        source = _source(name)
        if source is not None:
            canonical_source = _part(source)
            if canonical_source is None or canonical_source not in parts:
                out.append(("invalid-relationship-source", name, "source", source)); continue
        else: canonical_source = None
        root = ET.fromstring(payloads[name]); namespace = root.tag.partition("}")[0][1:]
        if root.tag != _REL_TAG: out.append(("invalid-relationships-namespace", name, "namespace", namespace)); continue
        for child in root:
            a = child.attrib
            for field in ("Id", "Type", "Target"):
                if field not in a: out.append(("missing-relationship-attribute", name, field, ""))
            if child.tag != _CHILD: out.append(("invalid-relationships-child", name, "tag", child.tag)); continue
            identifier, type_uri, target, mode = a.get("Id"), a.get("Type"), a.get("Target"), a.get("TargetMode", "Internal")
            if identifier is not None and (not identifier or identifier[0].isdigit() or "%" in identifier): out.append(("invalid-relationship-id", canonical_source or name, "Id", identifier))
            if type_uri is not None and not ("://" in type_uri and " " not in type_uri): out.append(("invalid-relationship-type", canonical_source or name, "Type", type_uri))
            if target is not None and mode == "Internal":
                resolved = _resolve(canonical_source, target)
                if resolved is None: out.append(("invalid-relationship-target", canonical_source or name, "Target", target))
                elif resolved not in parts: out.append(("missing-internal-target", canonical_source or name, "Target", target))
            if mode not in {"Internal", "External"}: out.append(("invalid-target-mode", canonical_source or name, "TargetMode", mode))
    return tuple(out)
