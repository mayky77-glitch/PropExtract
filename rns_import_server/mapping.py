"""Optional, local-only field mapping for already extracted candidates.

The current RNS extractor emits no candidates, so this integrated seam is
dormant by default. Activating it requires future owner-approved candidate
generation and a labelled benchmark: mapping may fill missing values that can
then reach Excel. It never reads PDFs, validates values, resolves Excel
conflicts, or writes a workbook.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


TARGET_FIELDS = frozenset((
    "issue", "end", "changed", "issuer", "developer", "builder",
    "district", "region", "stage", "object",
))
_TIMEOUT_SECONDS = 3
_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_CANDIDATES = 16
_MAX_CANDIDATE_ID_CHARS = 128
_MAX_CANDIDATE_VALUE_CHARS = 1024
_MAX_ALLOWED_TARGETS = len(TARGET_FIELDS)
_MAX_CANDIDATES_BYTES = 16 * 1024
_MAX_REQUEST_BYTES = 48 * 1024
_LOOPBACK_PROXY_HANDLER = urllib.request.ProxyHandler({})
_LOOPBACK_OPENER = urllib.request.build_opener(_LOOPBACK_PROXY_HANDLER)
_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["assignments"],
    "properties": {"assignments": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "target"],
        "properties": {
            "candidate_id": {"type": "string"},
            "target": {"type": "string", "enum": sorted(TARGET_FIELDS)},
        },
    }}},
}


def _endpoint() -> tuple[str, str] | None:
    """Return only an explicitly configured exact Ollama loopback endpoint."""
    endpoint, model = os.environ.get("RNS_MAPPING_LLM_ENDPOINT", ""), os.environ.get("RNS_MAPPING_LLM_MODEL", "")
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username is not None or parsed.password is not None
        or port is None or parsed.path != "/api/chat" or parsed.query
        or parsed.fragment or not model.strip()
    ):
        return None
    return endpoint, model.strip()


def _candidates(record: dict[str, object]) -> list[dict[str, object]]:
    """Accept only explicit candidate objects emitted by a future extractor."""
    raw = record.get("mapping_candidates")
    if not isinstance(raw, list) or not raw or len(raw) > _MAX_CANDIDATES:
        return []
    candidates: list[dict[str, object]] = []
    ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            return []
        candidate_id, value, targets = item.get("id"), item.get("value"), item.get("allowed_targets")
        if (
            not isinstance(candidate_id, str) or not candidate_id or len(candidate_id) > _MAX_CANDIDATE_ID_CHARS
            or candidate_id in ids or not isinstance(value, str) or not value or len(value) > _MAX_CANDIDATE_VALUE_CHARS
            or not isinstance(targets, list) or not targets or len(targets) > _MAX_ALLOWED_TARGETS
            or any(not isinstance(target, str) or target not in TARGET_FIELDS for target in targets)
            or len(set(targets)) != len(targets)
        ):
            return []
        ids.add(candidate_id)
        candidates.append({"id": candidate_id, "value": value, "allowed_targets": sorted(targets)})
    try:
        serialized = json.dumps(candidates, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return []
    return candidates if len(serialized) <= _MAX_CANDIDATES_BYTES else []


def _request(endpoint: str, model: str, candidates: list[dict[str, object]]) -> dict[str, Any] | None:
    payload = {
        "model": model, "stream": False, "keep_alive": "0", "think": False,
        "options": {"temperature": 0, "num_ctx": 1024, "num_predict": 128}, "format": _SCHEMA,
        "messages": [{
            "role": "user",
            "content": (
                "Map every candidate to exactly one target field. Return JSON only. "
                "Do not alter, normalize, validate, or invent values. "
                f"Candidates: {json.dumps(candidates, ensure_ascii=False)}"
            ),
        }],
    }
    try:
        encoded_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return None
    if len(encoded_payload) > _MAX_REQUEST_BYTES:
        return None
    request = urllib.request.Request(endpoint, data=encoded_payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _LOOPBACK_OPENER.open(request, timeout=_TIMEOUT_SECONDS) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > _MAX_RESPONSE_BYTES:
                return None
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                return None
            body = json.loads(raw.decode("utf-8"))
        if not isinstance(body, dict):
            return None
        message = body.get("message")
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        decision = json.loads(content) if isinstance(content, str) else None
        return decision if isinstance(decision, dict) else None
    except (OSError, ValueError, TypeError, UnicodeError, urllib.error.URLError, json.JSONDecodeError):
        return None


def map_extracted_record(record: dict[str, object]) -> dict[str, object]:
    """Map supplied candidates or return the original record unchanged.

    Invalid service output, timeout, unavailable service, or incomplete mapping
    is a fail-closed no-op. Returned values always originate from candidates;
    no model output becomes an Excel value. Mapping can fill missing fields
    only; it must remain opt-in because those values can reach Excel later.
    """
    configured, candidates = _endpoint(), _candidates(record)
    if configured is None or not candidates:
        return record
    decision = _request(*configured, candidates)
    assignments = decision.get("assignments") if isinstance(decision, dict) else None
    if not isinstance(assignments, list) or len(assignments) != len(candidates):
        return record
    values = {str(item["id"]): str(item["value"]) for item in candidates}
    allowed = {str(item["id"]): set(item["allowed_targets"]) for item in candidates}
    mapped: dict[str, str] = {}
    assigned_ids: set[str] = set()
    for item in assignments:
        if not isinstance(item, dict):
            return record
        candidate_id, target = item.get("candidate_id"), item.get("target")
        if (
            not isinstance(candidate_id, str) or candidate_id not in values
            or candidate_id in assigned_ids or target not in allowed[candidate_id]
            or target in mapped or record.get(target) not in (None, "")
        ):
            return record
        mapped[target] = values[candidate_id]
        assigned_ids.add(candidate_id)
    if assigned_ids != set(values) or len(mapped) != len(candidates):
        return record
    resolved = dict(record)
    resolved.update(mapped)
    provenance = dict(record.get("field_provenance", {})) if isinstance(record.get("field_provenance"), dict) else {}
    provenance.update({field: "mapping_llm" for field in mapped})
    resolved["field_provenance"] = provenance
    warnings = record.get("warnings")
    if isinstance(warnings, list):
        resolved["warnings"] = [item for item in warnings if item not in mapped]
    return resolved
