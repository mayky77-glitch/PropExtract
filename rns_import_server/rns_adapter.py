"""RNS record parsing.  The rules identify only text present in a document."""
from __future__ import annotations

import calendar
import re
from statistics import median
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
    r"номер\s+разрешения\s+на\s+строительство|"
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
    cleaned = re.sub(r"(^|\s)\|+\s*", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
    cleaned = re.sub(r"(?<=\w)-\s+(?=\w)", "-", cleaned)
    return cleaned or None


def _clean_district(value: str | None) -> str | None:
    cleaned = _clean_field(value)
    if not cleaned:
        return None
    cleaned = re.sub(r"^округ,?\s+(?=[А-ЯЁ])", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^иркутская\s+область\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:в\s+)?составе$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+в$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+муниципальн\w*\s+район\w*$", " район", cleaned, flags=re.IGNORECASE)
    if re.fullmatch(r"[А-ЯЁ][А-Яа-яЁё-]+(?:ский|ской|цкий|цкой)", cleaned):
        cleaned += " район"
    return cleaned


def _line_boundary(line: object) -> float | None:
    words = getattr(line, "words", ())
    page_width = int(getattr(line, "page_width", 0))
    if len(words) < 2 or not page_width:
        return None
    candidates: list[tuple[int, float]] = []
    for left, right in zip(words, words[1:]):
        gap = right.left - (left.left + left.width)
        midpoint = left.left + left.width + gap / 2
        if gap >= max(45, page_width * 0.035) and page_width * 0.28 <= midpoint <= page_width * 0.75:
            candidates.append((gap, midpoint))
    return max(candidates)[1] if candidates else None


def _page_boundary(lines: tuple[object, ...], page: int) -> float | None:
    candidates = [boundary for line in lines if getattr(line, "page", 0) == page if (boundary := _line_boundary(line))]
    if not candidates:
        return None
    page_width = next((int(getattr(line, "page_width", 0)) for line in lines if getattr(line, "page", 0) == page), 0)
    bin_width = max(40, page_width // 20)
    bins: dict[int, list[float]] = {}
    for boundary in candidates:
        bins.setdefault(round(boundary / bin_width), []).append(boundary)
    cluster = max(bins.values(), key=lambda values: (len(values), -abs(median(values) - page_width / 2)))
    return float(median(cluster))


def _column_parts(line: object, boundary: float) -> tuple[str, str]:
    left: list[str] = []
    right: list[str] = []
    for word in getattr(line, "words", ()):
        target = right if word.left + word.width / 2 > boundary else left
        target.append(word.text)
    return " ".join(left), " ".join(right)


def _geometry_label_block(text: str, labels: str) -> str | None:
    """Use left-column labels to collect only right-column values."""
    lines = tuple(getattr(text, "lines", ()))
    if not lines:
        return None
    label_pattern = re.compile(rf"(?:{labels})\b", re.IGNORECASE)
    page_boundaries = {
        page: _page_boundary(lines, page)
        for page in {getattr(line, "page", 0) for line in lines}
    }
    for index, line in enumerate(lines):
        local = _line_boundary(line)
        fallback = page_boundaries.get(getattr(line, "page", 0))
        boundary = local or fallback
        if boundary is None:
            continue
        left, right = _column_parts(line, boundary)
        if not label_pattern.search(left):
            continue
        values = [right] if right else []
        previous = index - 1
        while previous >= 0 and getattr(lines[previous], "page", 0) == getattr(line, "page", 0):
            previous_left, previous_right = _column_parts(lines[previous], boundary)
            if previous_left:
                break
            if previous_right:
                values.insert(0, previous_right)
            previous -= 1
        anchor_number = re.match(r"\s*(\d+(?:[.-]\d+)+)", left)
        following = index + 1
        while following < len(lines) and getattr(lines[following], "page", 0) == getattr(line, "page", 0):
            following_left, following_right = _column_parts(lines[following], boundary)
            next_number = re.match(r"\s*(\d+(?:[.-]\d+)+)", following_left)
            if next_number and (not anchor_number or next_number.group(1) != anchor_number.group(1)):
                break
            boundary_match = _BOUNDARY.search("\n" + following_left) if following_left else None
            if boundary_match and not label_pattern.search(following_left):
                break
            if following_right:
                values.append(following_right)
            following += 1
        return _clean_field(" ".join(values))
    return None


def _label_block(text: str, labels: str, limit: int = 700) -> str | None:
    """Read a value bounded by known form labels without changing raw OCR text."""
    if geometric := _geometry_label_block(text, labels):
        return geometric
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


_RNS_NUMBER_LABEL = r"номер\s+разрешения\s+на\s+строительство"
_REORDERED_RNS_LINE_LABEL = re.compile(
    r"^\s*(?:[|¦]?\s*[-–—]?\s*\d+(?:[.-]\d+)*[.)]?\s*)?"
    r"строительство\s*:\s*номер\s+разрешения\s+на\b",
    re.IGNORECASE,
)


def _reordered_rns_line_evidence(text: str) -> tuple[tuple[str, ...], bool]:
    """Read only the proven reversed table-label grammar on one OCR line."""
    geometry_lines = tuple(getattr(text, "lines", ()))
    lines = tuple(line.text for line in geometry_lines) if geometry_lines else tuple(str(text).splitlines())
    candidates: list[tuple[str, ...]] = []
    for line in lines:
        if not _REORDERED_RNS_LINE_LABEL.search(line):
            continue
        identities = canonical_rns_identities(line)
        if identities:
            candidates.append(identities)
    ambiguous = len(candidates) > 1 or any(len(identities) != 1 for identities in candidates)
    identities = tuple(dict.fromkeys(identity for candidate in candidates for identity in candidate))
    return identities, ambiguous


def _labeled_rns_evidence(text: str) -> tuple[tuple[str, ...], bool]:
    """Read identities from bounded RNS-number form fields only."""
    pattern = re.compile(
        rf"(?:^|\n)\s*(?:[1-9]\d?(?:[.-]\d{{1,2}}){{0,2}}[.)]?\s*)?(?:{_RNS_NUMBER_LABEL})\s*[:№-]?\s*",
        re.IGNORECASE,
    )
    identities: list[str] = []
    for match in pattern.finditer(text):
        value = text[match.end():match.end() + 240]
        boundary = _BOUNDARY.search("\n" + value)
        if boundary:
            value = value[:boundary.start()]
        identities.extend(canonical_rns_identities(value))
    reordered_identities, reordered_ambiguity = _reordered_rns_line_evidence(text)
    identities.extend(reordered_identities)
    combined = tuple(dict.fromkeys(identities))
    return combined, reordered_ambiguity or len(combined) > 1


def date(value: str | None) -> datetime | None:
    return datetime.strptime(value, "%d.%m.%Y") if value else None


def norm(pdf: Path, text: str) -> str | None:
    """Read a complete RNS number from content, then a complete filename fallback."""
    content_identities = canonical_rns_identities(text)
    labeled_identities, labeled_ambiguity = _labeled_rns_evidence(text)
    if labeled_ambiguity:
        return None
    if len(labeled_identities) == 1:
        return labeled_identities[0]
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
    values, _ = _valid_dates(_DATE_RE.findall(value or ""))
    return max(values, key=lambda item: date(item) or datetime.min) if values else None


def _valid_dates(values: list[str]) -> tuple[list[str], bool]:
    """Keep impossible OCR calendar values document-local and non-authoritative."""
    valid: list[str] = []
    invalid = False
    for value in values:
        try:
            if date(value) is not None:
                valid.append(value)
        except (TypeError, ValueError):
            invalid = True
    return valid, invalid


_QUALITY_ANCHORS = {
    "issue": r"дата\s+(?:выдачи\s+)?разрешения|дата\s+выдачи",
    "end": r"срок\s+действия|\bдо\s*\d{2}\.\d{2}\.20\d{2}",
    "changed": r"дата\s+(?:последн\w*\s*)?(?:измен\w*|внесения\s+измен\w*)|изменения",
    "issuer": r"наименование\s+органа|орган\s+(?:выдачи|местного\s+самоуправления)",
    "developer": r"разработчик\s+пд|проектн\w*\s+организац\w*",
    "builder": r"застройщик",
    "district": r"муниципальн\w*\s+район",
    "region": r"субъект\s+рф",
    "stage": r"этап",
    "object": r"наименование\s+объекта|объект(?:\s+капитального\s+строительства)?",
}


def _quality_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[\wЁё]+", value.casefold()))


def _field_value_grammar(field: str, value: str) -> bool:
    """Require the small field shapes that make OCR evidence transferable."""
    normalized = _clean_field(value) or ""
    if field in {"issue", "end", "changed"}:
        return bool(re.fullmatch(_DATE, normalized))
    if field == "stage":
        return bool(re.fullmatch(r"этап\s*\d+(?:\.\d+)+", normalized, re.IGNORECASE))
    if field == "district":
        return bool(re.search(r"\b(?:район|округ|муниципальн\w*\s+образован\w*)\b", normalized, re.IGNORECASE))
    if field in {"developer", "builder"}:
        return bool(re.match(r"\s*(?:ооо|пао|ао|ип|общество\s+с\s+ограниченной|акционерное\s+общество)\b", normalized, re.IGNORECASE))
    if field == "issuer":
        return bool(re.match(r"\s*(?:администрац|министерств|служб|комитет|департамент|управлен)", normalized, re.IGNORECASE))
    return bool(_quality_tokens(normalized))


def _contiguous_line_evidence(text: object, anchor: str, value: str) -> tuple[list[object], str | None]:
    """Find a label and its value only in the same or next OCR line/window."""
    lines = tuple(getattr(text, "lines", ()))
    expected = _quality_tokens(value)
    if not lines:
        return [], "missing_geometry_evidence"
    saw_anchor = False
    for index, line in enumerate(lines):
        line_text = getattr(line, "text", "")
        anchor_match = re.search(anchor, line_text, re.IGNORECASE)
        if not anchor_match:
            continue
        saw_anchor = True
        line_words = list(getattr(line, "words", ()))
        # OCRLine.text joins word text with single spaces. Locate the first
        # word whose textual span ends after the matched label and accept only
        # words after that boundary; prefix/reference text is never a value.
        cursor = 0
        first_after_anchor = len(line_words)
        for word_index, word in enumerate(line_words):
            word_text = getattr(word, "text", "")
            word_start = cursor
            word_end = word_start + len(word_text)
            cursor = word_end + 1
            if word_start >= anchor_match.end():
                first_after_anchor = word_index
                break
        words = line_words[first_after_anchor:]
        if index + 1 < len(lines) and getattr(lines[index + 1], "page", 0) == getattr(line, "page", 0):
            words.extend(getattr(lines[index + 1], "words", ()))
        observed = _quality_tokens(" ".join(getattr(word, "text", "") for word in words))
        if not expected or not any(observed[offset:offset + len(expected)] == expected for offset in range(len(observed) - len(expected) + 1)):
            continue
        evidence: list[object] = []
        for offset in range(len(observed) - len(expected) + 1):
            if observed[offset:offset + len(expected)] == expected:
                token_offset = 0
                for word in words:
                    tokens = _quality_tokens(getattr(word, "text", ""))
                    if token_offset + len(tokens) > offset and token_offset < offset + len(expected):
                        evidence.append(word)
                    token_offset += len(tokens)
                return evidence, None
    return [], "missing_contiguous_value_evidence" if saw_anchor else "missing_label_anchor"


def _field_quality(text: str, record: dict[str, object]) -> dict[str, dict[str, object]]:
    """Fail closed unless local geometry proves a label/value relationship."""
    if getattr(text, "source", None) != "raster":
        return {}
    quality: dict[str, dict[str, object]] = {}
    for field, anchor in _QUALITY_ANCHORS.items():
        value = record.get(field)
        if not isinstance(value, str) or not value:
            continue
        provenance = record.get("field_provenance", {})
        if not isinstance(provenance, dict) or provenance.get(field) != "ocr":
            continue
        if "�" in value or "…" in value or re.search(r"(?:\.\.\.|[-/])\s*$", value):
            quality[field] = {"status": "review", "reason": "obvious_ocr_truncation"}
            continue
        if not _field_value_grammar(field, value):
            quality[field] = {"status": "review", "reason": "invalid_field_grammar"}
            continue
        evidence, failure = _contiguous_line_evidence(text, anchor, value)
        if failure:
            quality[field] = {"status": "review", "reason": failure}
            continue
        confidence = round(max(0.0, min(100.0, min(float(word.confidence) for word in evidence))), 1)
        quality[field] = {
            "status": "actionable" if confidence >= 55.0 else "review",
            "reason": "ocr_geometry" if confidence >= 55.0 else "low_ocr_confidence",
            "confidence": confidence,
        }
    return quality


def add_months(value: str, months: int) -> str:
    source = date(value)
    assert source is not None
    month_index = source.month - 1 + months
    year, month = source.year + month_index // 12, month_index % 12 + 1
    return datetime(year, month, min(source.day, calendar.monthrange(year, month)[1])).strftime("%d.%m.%Y")


def _explicit_extension_end(pdf: Path) -> str | None:
    """Trust an explicit filename deadline only when the file names a prolongation."""
    if not re.search(r"продл(?:ен|ён|ить|ение)", pdf.stem, re.IGNORECASE):
        return None
    return find(pdf.stem, rf"\bдо\s*{_DATE}")


def extract(pdf: Path, text: str, number: str | None = None) -> dict[str, object] | None:
    """Extract direct RNS fields.  ``number`` is test/API input, never an inference."""
    content_identities = canonical_rns_identities(text)
    labeled_identities, labeled_ambiguity = _labeled_rns_evidence(text)
    filename_identities = canonical_rns_identities(pdf.stem)
    if number is None:
        if labeled_ambiguity:
            return None
        if len(labeled_identities) == 1:
            number = labeled_identities[0]
        elif len(content_identities) > 1:
            return None
        else:
            number = content_identities[0] if content_identities else (filename_identities[0] if len(filename_identities) == 1 else None)
    if not number:
        return None
    issue_labels = r"дата\s+(?:выдачи\s+)?разрешения(?:\s+на\s+строительство)?|дата\s+выдачи"
    issue_block = _label_block(text, issue_labels)
    issue_dates = _label_dates(text, issue_labels)
    issue_candidates = issue_dates + _DATE_RE.findall(issue_block or "")
    issue_fallback = find(text, rf"1[.-]1[\s\S]{{0,120}}?:\s*\[?\s*{_DATE}")
    if issue_fallback:
        issue_candidates.append(issue_fallback)
    valid_issue_dates, invalid_issue = _valid_dates(issue_candidates)
    filename_issue = find(pdf.name, _DATE)
    valid_filename_issue, invalid_filename_issue = _valid_dates([filename_issue] if filename_issue else [])
    invalid_issue = invalid_issue or invalid_filename_issue
    issue = valid_issue_dates[0] if valid_issue_dates else (valid_filename_issue[0] if valid_filename_issue else None)
    issue_from_filename = not valid_issue_dates and bool(valid_filename_issue)
    validity_labels = r"срок\s+действия(?:\s+настоящего)?\s+разрешения|срок\s+действия"
    validity_block = _label_block(text, validity_labels)
    months = re.search(r"\b(\d+)\s*месяц", validity_block or "", re.IGNORECASE)
    validity_dates = _label_dates(text, validity_labels)
    extension_end = _explicit_extension_end(pdf)
    end_candidates = ([extension_end] if extension_end else []) + validity_dates + _DATE_RE.findall(validity_block or "")
    valid_end_dates, invalid_end = _valid_dates(end_candidates)
    # An unlabelled ``до DD.MM.YYYY`` remains a last-resort document hint. It
    # must not outrank a scanned validity field unless the filename expressly
    # says this is a prolongation.
    if not valid_end_dates:
        explicit_end = find(pdf.name + "\n" + text, rf"до\s*{_DATE}")
        if explicit_end:
            fallback_end_dates, fallback_invalid = _valid_dates([explicit_end])
            valid_end_dates.extend(fallback_end_dates)
            invalid_end = invalid_end or fallback_invalid
    end = (
        extension_end
        if extension_end and extension_end in valid_end_dates
        else (valid_end_dates[-1] if valid_end_dates else (add_months(issue, int(months.group(1))) if issue and months else None))
    )
    changed_labels = r"дата\s+(?:последн\w*\s*)?(?:измен\w*|внесения\s+измен\w*)|изменения"
    changed_block = _label_block(text, changed_labels)
    changed_dates = _label_dates(text, changed_labels)
    changed_values = changed_dates + _DATE_RE.findall(changed_block or "") + re.findall(
        rf"1\.[5-9][\s\S]{{0,120}}?:\s*{_DATE}", text, re.IGNORECASE
    )
    valid_changed_dates, invalid_changed = _valid_dates(changed_values)
    changed = max(valid_changed_dates, key=lambda item: date(item) or datetime.min) if valid_changed_dates else None
    issuer = _label_block(text, r"наименование\s+органа(?:\s*\(организации\))?|орган\s+(?:выдачи|местного\s+самоуправления)") or one(text, r"(?:Администрация|Служба)[\s\S]{0,260}?(?:район\w*|области)")
    builder = _label_block(text, r"застройщик") or one(text, r"ПАО\s*[«\"]?Газпром[»\"]?")
    developer = _label_block(text, r"разработчик\s+пд|проектн\w*\s+организац\w*") or one(text, r"(?:ООО|Общество\s+с\s+ограниченной)[\s\S]{0,150}?Газпром\s+проектировани\S*")
    region = _label_block(text, r"субъект\s+рф") or ("Иркутская область" if "ИРКУТСКАЯ ОБЛАСТЬ" in text.upper() else None)
    district = _clean_district(_label_block(text, r"муниципальн\w*\s+район")) or ("Жигаловский район" if "Жигалов" in text else "Казачинско-Ленский район" if "Казачинско" in text else None)
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
        "number_source": "content" if (
            (len(content_identities) == 1 and content_identities[0] == number)
            or (len(labeled_identities) == 1 and labeled_identities[0] == number)
        ) else "filename",
        "field_provenance": {"issue": "filename" if issue_from_filename else "ocr"} if issue else {},
    }
    record["field_provenance"] = {key: "ocr" for key in ("end", "changed", "issuer", "developer", "builder", "district", "region", "stage", "object") if record.get(key)} | record["field_provenance"]
    if end == extension_end and extension_end in valid_end_dates:
        record["field_provenance"]["end"] = "filename"
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
    for field, invalid in (("issue", invalid_issue), ("end", invalid_end), ("changed", invalid_changed)):
        if invalid:
            record["warnings"].append(f"invalid_date:{field}")
    if quality := _field_quality(text, record):
        record["field_quality"] = quality
    return record
