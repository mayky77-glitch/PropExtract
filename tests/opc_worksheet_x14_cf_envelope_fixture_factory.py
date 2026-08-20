"""Compact valid and malformed X14 CF envelope fixture helpers."""
from __future__ import annotations

from pathlib import Path

from tests.opc_worksheet_x14_cf_owner_fixture_factory import CF_URI, package, worksheet


def rule(*, priority: str = "1", stop: str | None = None, rule_id: str = "{01234567-89Ab-cDef-0123-456789aBcDeF}", formula: str = "A1>0", dxf: str = "<x14:dxf><font/></x14:dxf>") -> str:
    stop_attr = "" if stop is None else f' stopIfTrue="{stop}"'
    return f'<x14:cfRule type="expression" priority="{priority}" id="{rule_id}"{stop_attr}><xm:f>{formula}</xm:f>{dxf}</x14:cfRule>'


def container(rules: str | None = None, sqref: str = "A1") -> str:
    return f'<x14:conditionalFormatting>{rules or rule()}<xm:sqref>{sqref}</xm:sqref></x14:conditionalFormatting>'


def cf(containers: str) -> str:
    return f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>{containers}</x14:conditionalFormattings></ext></extLst>'


def envelope_package(destination: Path, *, first: str, second: str = "") -> Path:
    return package(destination, sheet_one=worksheet(first), sheet_two=worksheet(second))
