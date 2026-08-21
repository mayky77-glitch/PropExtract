"""Synthetic OPC corpus helpers for the frozen X2a rule-envelope gate."""
from __future__ import annotations

from pathlib import Path

from tests.opc_worksheet_x14_cf_owner_fixture_factory import CF_URI, X14, XM, package, worksheet


def extension(containers: str) -> str:
    return (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>'
            f'{containers}</x14:conditionalFormattings></ext></extLst>')


def owner(*rules: str, sqref: str = "<xm:sqref>A1</xm:sqref>") -> str:
    return f'<x14:conditionalFormatting>{"".join(rules)}{sqref}</x14:conditionalFormatting>'


def rule(*, priority: str = "1", rule_id: str = "{00112233-4455-6677-8899-AABBCCDDEEFF}",
         formula: str = "A1&gt;0", stop: str | None = None, children: str | None = None,
         extra: str = "") -> str:
    stop_attr = "" if stop is None else f' stopIfTrue="{stop}"'
    content = children if children is not None else f'<xm:f>{formula}</xm:f><x14:dxf/>'
    return f'<x14:cfRule type="expression" priority="{priority}" id="{rule_id}"{stop_attr}{extra}>{content}</x14:cfRule>'


def corpus(destination: Path, *, first: str, second: str = "") -> Path:
    return package(destination, sheet_one=worksheet(first), sheet_two=worksheet(second))
