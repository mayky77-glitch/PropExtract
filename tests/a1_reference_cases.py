"""Shared, visibly distinct A1 mapping cases for insertion boundaries."""
from __future__ import annotations


MAPPING_CASES = (
    # Boundary 6: above, at, below and spanning ranges.
    ("=A5+A6+A7+A5:A7", "Target", "Target", 6, "=A5+A7+A8+A5:A8"),
    # Boundary 10: all anchor variants remain byte-exact apart from rows.
    ("=$A$9+A$10+$A10+$A$11", "Target", "Target", 10, "=$A$9+A$11+$A11+$A$12"),
    # Boundary 104: wholly-below ranges shift, spanning ranges expand.
    ("=B104:B105+C103:C104", "Target", "Target", 104, "=B105:B106+C103:C105"),
    # Whole-row and whole-column forms are structurally distinct.
    ("=5:7+A:C", "Target", "Target", 6, "=5:8+A:C"),
    # Local host references move only when the host is the target.
    ("=A10", "Other", "Target", 10, "=A10"),
    # Qualified unquoted and quoted sheets compare semantic sheet names.
    ("=Target!A10+'O''Brien'!$B$10+Other!C10", "Host", "o'brien", 10,
     "=Target!A10+'O''Brien'!$B$11+Other!C10"),
)


UNSUPPORTED_CASES = (
    "=[Book.xlsx]Target!A10+Target!A10",
    "='[Book.xlsx]Target'!A10+Target!A10",
    "=Target:Other!A10+Target!A10",
    "=Table1[Amount]+A10",
)
