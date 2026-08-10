"""RNS record parsing.  The rules identify only text present in a document."""
from __future__ import annotations

import calendar
import re
from datetime import datetime
from pathlib import Path

try:
    from rns_import_server.normalization import canonical_rns_identity, canonical_rns_identities
except ModuleNotFoundError:  # Direct ``python rns_import_server/app.py`` invocation.
    from normalization import canonical_rns_identity, canonical_rns_identities

_DATE = r"(\d{2}\.\d{2}\.20\d{2})"
_DATE_RE = re.compile(_DATE)
_BOUNDARY = re.compile(
    r"(?:^|\n)\s*(?:[1-9]\d?(?:[.-]\d{1,2}){0,2}[.)]?\s*)?(?:дата\s+(?:выдачи|разрешения)|срок\s+действия|"
    r"дата\s+(?:последн\w*\s*)?(?:измен\w*|внесения)|наименование\s+(?:объекта|застройщика)|"
    r"объект(?:\s+капитального\s+строительства)?|орган\s+(?:выдачи|местного)|застройщик|"
    r"разработчик\s+пд|проектн\w*\s+организац\w*|субъект\s+рф|муниципальн\w*\s+район|"
    r"этап)\b",
    re.IGNORECASE,
)


def _clean_field(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[\x00\f]+", " ", value)
    cleaned = re.sub(r"(?:страниц[аы]|лист)\s*\d+(?:\s*(?:из|/|\s)\s*\d+)?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
    return cleaned or None


def _label_block(text: str, labels: str, limit: int = 700) -> str | None:
    """Read a value bounded by known form labels without changing raw OCR text."""
    match = re.search(rf"(?:^|\n)\s*(?:[1-9]\d?(?:[.-]\d{{1,2}}){{0,2}}[.)]?\s*)?(?:{labels})\s*[:№-]?\s*", text, re.IGNORECASE)
    if not match:
        return None
    value = text[match.end():match.end() + limit]
    boundary = _BOUNDARY.search("\n" + value)
    if boundary:
        value = value[:boundary.start()]
    return _clean_field(value)


def _label_dates(text: str, labels: str) -> list[str]:
    """Read dates from every known label block, tolerating table columns."""
    pattern = re.compile(
        rf"(?:^|\n)[^\n]{{0,80}}?(?:{labels})\b",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    dates: list[str] = []
    for index, match in enumerate(matches):
        value = text[match.end():match.end() + 240]
        boundary = _BOUNDARY.search("\n" + value)
        if boundary:
            value = value[:boundary.start()]
        dates.extend(_DATE_RE.findall(value))
    return dates


def date(value: str | None) -> datetime | None:
    return datetime.strptime(value, "%d.%m.%Y") if value else None


def norm(pdf: Path, text: str) -> str | None:
    """Read a complete RNS number from content, then a complete filename fallback."""
    content_identities = canonical_rns_identities(text)
    if len(content_identities) > 1:
        return None
    if content_identities:
        return content_identities[0]
    return canonical_rns_identity(pdf.stem)


def find(text: str, *patterns: str) -> str | None:
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return match.group(1)
    return None


def one(text: str, pattern: str) -> str | None:
    if match := re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        return re.sub(r"\s+", " ", match.group(0)).strip(" .,;")
    return None


def _first_date(value: str | None) -> str | None:
    return _DATE_RE.search(value).group(1) if value and _DATE_RE.search(value) else None


def _last_date(value: str | None) -> str | None:
    values = _DATE_RE.findall(value or "")
    return max(values, key=lambda item: date(item) or datetime.min) if values else None


def add_months(value: str, months: int) -> str:
    source = date(value)
    assert source is not None
    month_index = source.month - 1 + months
    year, month = source.year + month_index // 12, month_index % 12 + 1
    return datetime(year, month, min(source.day, calendar.monthrange(year, month)[1])).strftime("%d.%m.%Y")


def extract(pdf: Path, text: str, number: str | None = None) -> dict[str, object] | None:
    """Extract direct RNS fields.  ``number`` is test/API input, never an inference."""
    content_identities = canonical_rns_identities(text)
    filename_identities = canonical_rns_identities(pdf.stem)
    if number is None:
        if len(content_identities) > 1:
            return None
        number = content_identities[0] if content_identities else (filename_identities[0] if len(filename_identities) == 1 else None)
    if not number:
        return None
    issue_labels = r"дата\s+(?:выдачи\s+)?разрешения(?:\s+на\s+строительство)?|дата\s+выдачи"
    issue_block = _label_block(text, issue_labels)
    issue_dates = _label_dates(text, issue_labels)
    issue = (issue_dates[0] if issue_dates else None) or _first_date(issue_block) or find(text, rf"1[.-]1[\s\S]{{0,120}}?:\s*\[?\s*{_DATE}")
    if not issue:
        issue = find(pdf.name, _DATE)
    validity_labels = r"срок\s+действия(?:\s+настоящего)?\s+разрешения|срок\s+действия"
    validity_block = _label_block(text, validity_labels)
    months = re.search(r"\b(\d+)\s*месяц", validity_block or "", re.IGNORECASE)
    validity_dates = _label_dates(text, validity_labels)
    end = (validity_dates[-1] if validity_dates else None) or _last_date(validity_block) or (add_months(issue, int(months.group(1))) if issue and months else find(pdf.name + "\n" + text, rf"до\s*{_DATE}"))
    changed_labels = r"дата\s+(?:последн\w*\s*)?(?:измен\w*|внесения\s+измен\w*)|изменения"
    changed_block = _label_block(text, changed_labels)
    changed_dates = _label_dates(text, changed_labels)
    changed = max(changed_dates, key=lambda item: date(item) or datetime.min) if changed_dates else _last_date(changed_block)
    if not changed:
        changed_values = re.findall(rf"1\.[5-9][\s\S]{{0,120}}?:\s*{_DATE}", text, re.IGNORECASE)
        changed = max(changed_values, key=lambda item: date(item) or datetime.min) if changed_values else None
    issuer = _label_block(text, r"орган\s+(?:выдачи|местного\s+самоуправления)") or one(text, r"(?:Администрация|Служба)[\s\S]{0,260}?(?:район\w*|области)")
    builder = _label_block(text, r"застройщик") or one(text, r"ПАО\s*[«\"]?Газпром[»\"]?")
    developer = _label_block(text, r"разработчик\s+пд|проектн\w*\s+организац\w*") or one(text, r"(?:ООО|Общество\s+с\s+ограниченной)[\s\S]{0,150}?Газпром\s+проектировани\S*")
    region = _label_block(text, r"субъект\s+рф") or ("Иркутская область" if "ИРКУТСКАЯ ОБЛАСТЬ" in text.upper() else None)
    district = _label_block(text, r"муниципальн\w*\s+район") or ("Жигаловский район" if "Жигалов" in text else "Казачинско-Ленский район" if "Казачинско" in text else None)
    record = {
        "number": number,
        "issue": issue,
        "end": end,
        "changed": changed,
        "issuer": issuer,
        "developer": developer,
        "builder": builder,
        "district": district,
        "region": region,
        "stage": one(text, r"Этап\s*\d+(?:\.\d+)+"),
        "object": _label_block(text, r"наименование\s+объекта|объект(?:\s+капитального\s+строительства)?") or one(text, r"(?:Обустройство|Строительство)[^\n]{30,400}"),
        "pdf": str(pdf.resolve()),
        "filename": pdf.name,
        "number_source": "content" if len(content_identities) == 1 and content_identities[0] == number else "filename",
        "field_provenance": {"issue": "filename" if issue and not issue_block else "ocr"} if issue else {},
    }
    record["field_provenance"] = {key: "ocr" for key in ("end", "changed", "issuer", "developer", "builder", "district", "region", "stage", "object") if record.get(key)} | record["field_provenance"]
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
