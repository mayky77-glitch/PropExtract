"""Synthetic OPC corpus helpers for the frozen X2b sqref-envelope gate."""
from __future__ import annotations

from pathlib import Path

from tests.opc_worksheet_x14_cf_rule_envelope_fixture_factory import extension, owner, rule
from tests.opc_worksheet_x14_cf_owner_fixture_factory import package, worksheet


def corpus(destination: Path, *, first: str, second: str = "") -> Path:
    return package(destination, sheet_one=worksheet(first), sheet_two=worksheet(second))


__all__ = ("corpus", "extension", "owner", "rule")
