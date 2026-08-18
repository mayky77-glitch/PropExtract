"""Read-only deterministic OOXML semantic inventory for insertion oracles."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib, re, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_CELL = re.compile(r"(?<![A-Z0-9_])(?P<colabs>\$?)(?P<col>[A-Z]{1,3})(?P<rowabs>\$?)(?P<row>\d+)")


class OOXMLSemanticError(RuntimeError): pass


@dataclass(frozen=True)
class OOXMLInventory:
    parts: tuple[tuple[str, str], ...]
    sheets: tuple[str, ...]
    formulas: tuple[str, ...]
    errors: tuple[str, ...]
    merges: tuple[str, ...]
    dimensions: tuple[str, ...]
    filters: tuple[str, ...]
    names: tuple[str, ...]
    native_rules: tuple[str, ...]


def map_cell(reference: str, insertion_row: int) -> str:
    match = _CELL.fullmatch(reference)
    if not match: raise OOXMLSemanticError("ooxml_cell_reference_invalid")
    value = int(match.group("row"))
    return f"{match.group('colabs')}{match.group('col')}{match.group('rowabs')}{value if value < insertion_row else value + 1}"


def map_formula(formula: str, insertion_row: int) -> str:
    if "[" in formula or "[#" in formula or ":" in formula and formula.count("!") > 1:
        raise OOXMLSemanticError("ooxml_formula_unsupported_reference")
    def replace(item: re.Match[str]) -> str:
        value = int(item.group("row")); mapped = value if value < insertion_row else value + 1
        return f"{item.group('colabs')}{item.group('col')}{item.group('rowabs')}{mapped}"
    return _CELL.sub(replace, formula)


def inventory(path: Path) -> OOXMLInventory:
    """Read ZIP bytes only; retain deterministic fingerprints for all XML parts."""
    with zipfile.ZipFile(path) as archive:
        names = sorted(archive.namelist()); parts = tuple((name, hashlib.sha256(archive.read(name)).hexdigest()) for name in names)
        xml = {name: archive.read(name).decode("utf-8", "replace") for name in names if name.endswith(".xml")}
    sheets = tuple(sorted(name for name in xml if name.startswith("xl/worksheets/sheet")))
    formulas = tuple(sorted(item for text in xml.values() for item in re.findall(r"<f[^>]*>(.*?)</f>", text)))
    errors = tuple(sorted(item for text in xml.values() for item in re.findall(r"#(?:REF!|VALUE!|NAME\?|DIV/0!|N/A)", text)))
    merges = tuple(sorted(item for text in xml.values() for item in re.findall(r"<mergeCell ref=\"([^\"]+)", text)))
    dimensions = tuple(sorted(item for text in xml.values() for item in re.findall(r"<dimension ref=\"([^\"]+)", text)))
    filters = tuple(sorted(item for text in xml.values() for item in re.findall(r"<autoFilter ref=\"([^\"]+)", text)))
    nameset = tuple(sorted(item for text in xml.values() for item in re.findall(r"<definedName[^>]*>(.*?)</definedName>", text)))
    native = tuple(sorted(hashlib.sha256(text.encode()).hexdigest() for text in xml.values() if "conditionalFormatting" in text or "x14:" in text or "dataValidations" in text))
    return OOXMLInventory(parts, sheets, formulas, errors, merges, dimensions, filters, nameset, native)
