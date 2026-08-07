"""RNS record parsing.  The rules identify only text present in a document."""
from __future__ import annotations

import calendar
import re
from datetime import datetime
from pathlib import Path

_SEPARATED_NUMBER = re.compile(r"\b(38)[-\s]+(\d{1,2})[-\s]+(\d{1,2})[-\s]+(20\d{2})\b")
_COMPACT_TEN_DIGIT_NUMBER = re.compile(r"\b(38)(\d{2})(\d{2})(20\d{2})\b")
_COMPACT_EIGHT_DIGIT_NUMBER = re.compile(r"\b(38)(\d)(\d)(20\d{2})\b")
_DATE = r"(\d{2}\.\d{2}\.20\d{2})"


def date(value: str | None) -> datetime | None:
    return datetime.strptime(value, "%d.%m.%Y") if value else None


def _format_number(match: re.Match[str]) -> str:
    """Keep the document's RNS group widths; never derive a number by slicing."""
    return "-".join(match.groups())


def norm(pdf: Path, text: str) -> str | None:
    """Read a complete RNS number from content, then a complete filename fallback."""
    for source in (text, pdf.stem):
        for pattern in (_SEPARATED_NUMBER, _COMPACT_TEN_DIGIT_NUMBER, _COMPACT_EIGHT_DIGIT_NUMBER):
            if match := pattern.search(source):
                return _format_number(match)
    return None


def find(text: str, *patterns: str) -> str | None:
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return match.group(1)
    return None


def one(text: str, pattern: str) -> str | None:
    if match := re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        return re.sub(r"\s+", " ", match.group(0)).strip(" .,;")
    return None


def add_months(value: str, months: int) -> str:
    source = date(value)
    assert source is not None
    month_index = source.month - 1 + months
    year, month = source.year + month_index // 12, month_index % 12 + 1
    return datetime(year, month, min(source.day, calendar.monthrange(year, month)[1])).strftime("%d.%m.%Y")


def extract(pdf: Path, text: str, number: str | None = None) -> dict[str, object] | None:
    """Extract direct RNS fields.  ``number`` is test/API input, never an inference."""
    number = number or norm(pdf, text)
    if not number:
        return None
    issue = find(
        text,
        rf"Дата\s+разрешения\s+на\s+строительство\s*:\s*\[?\s*{_DATE}",
        rf"1[.-]1[\s\S]{{0,120}}?:\s*\[?\s*{_DATE}",
    )
    if not issue:
        issue = find(pdf.name, _DATE)
    months = re.search(
        r"(?:1[.-]4|Срок\s+действия(?:\s+настоящего)?\s+разрешения)[\s\S]{0,100}?:\D{0,20}(\d+)\s*месяц",
        text,
        re.IGNORECASE,
    )
    end = add_months(issue, int(months.group(1))) if issue and months else find(pdf.name + "\n" + text, rf"до\s*{_DATE}")
    changed_values = re.findall(rf"1\.[5-9][\s\S]{{0,120}}?:\s*{_DATE}", text, re.IGNORECASE)
    changed = max(changed_values, key=lambda item: date(item) or datetime.min) if changed_values else None
    record = {
        "number": number,
        "issue": issue,
        "end": end,
        "changed": changed,
        "issuer": one(text, r"(?:Администрация|Служба)[\s\S]{0,260}?(?:район\w*|области)"),
        "developer": one(text, r"(?:ООО|Общество\s+с\s+ограниченной)[\s\S]{0,150}?Газпром\s+проектировани\S*"),
        "builder": one(text, r"ПАО\s*[«\"]?Газпром[»\"]?"),
        "district": "Жигаловский район" if "Жигалов" in text else "Казачинско-Ленский район" if "Казачинско" in text else None,
        "region": "Иркутская область" if "ИРКУТСКАЯ ОБЛАСТЬ" in text.upper() else None,
        "stage": one(text, r"Этап\s*\d+(?:\.\d+)+"),
        "object": one(text, r"(?:Обустройство|Строительство)[^\n]{30,400}"),
        "pdf": str(pdf.resolve()),
        "filename": pdf.name,
    }
    audited_fields = (
        "issue",
        "end",
        "changed",
        "issuer",
        "developer",
        "builder",
        "district",
        "region",
        "stage",
        "object",
    )
    record["warnings"] = [field for field in audited_fields if not record[field]]
    return record
