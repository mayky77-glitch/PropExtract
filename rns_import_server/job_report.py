"""Sanitized, atomic final-state enrichment for local import job reports."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from rns_import_server.new_row_payload import ImportedNewRowState, NewRowPayload, NewRowPayloadError, canonical_json, strict_json

try:
    from rns_import_server.audit import atomic_json
except ModuleNotFoundError:
    from audit import atomic_json


_SUMMARY_COUNTS = frozenset({
    "pdf_count", "failed_pdf_count", "record_count", "changed_rows", "review_rows",
    "new_rows", "already_present_count", "conflicts", "issue_count",
    "processed_rns_count", "out_of_scope_count", "unidentified_permit_count",
    "processing_failed_count",
})
_SUMMARY_ROWS = frozenset({"already_present_rows", "rows_with_issues", "row_numbers", "new_row_numbers"})


def report_path(target: Path) -> Path:
    return target.with_name(f"{target.stem} — отчет PropExtract.json")


def _safe_summary(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    report: dict[str, object] = {}
    for key in _SUMMARY_COUNTS:
        item = source.get(key)
        if isinstance(item, int) and not isinstance(item, bool):
            report[key] = item
    for key in _SUMMARY_ROWS:
        item = source.get(key)
        if isinstance(item, list) and all(isinstance(row, int) and not isinstance(row, bool) for row in item):
            report[key] = item
    return report


def _safe_actions(value: object) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    if not isinstance(value, list):
        return actions
    for item in value:
        if not isinstance(item, dict):
            continue
        kind, row, field, status = item.get("type"), item.get("row"), item.get("field"), item.get("status")
        if kind not in {"proposal_approved", "manual_edit"} or not isinstance(row, int) or not isinstance(field, str) or not isinstance(status, str):
            continue
        actions.append({"type": kind, "row": row, "field": field, "status": status})
    return actions


def _safe_warning(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    warning = " ".join(value.split())[:4000]
    return warning or None


def _safe_proposals(value: object) -> list[dict[str, object]]:
    return [
        {key: item[key] for key in ("row", "field", "status", "quality") if key in item and isinstance(item[key], (int, str, bool))}
        for item in value if isinstance(item, dict)
    ] if isinstance(value, list) else []


def _safe_row_cards(value: object) -> list[dict[str, object]]:
    return [
        {key: item[key] for key in ("row", "outcome", "needs_review", "edited") if key in item and isinstance(item[key], (int, str, bool))}
        for item in value if isinstance(item, dict)
    ] if isinstance(value, list) else []


def final_report_payload(job: dict[str, object]) -> dict[str, Any]:
    """Build a completed, allowlisted report from server-held safe state only."""
    target_hash = job.get("target_hash")
    if not isinstance(target_hash, str) or len(target_hash) != 64:
        raise ValueError("final_report_target_hash_missing")
    base = job.get("report_base_internal")
    if not isinstance(base, dict):
        raise ValueError("final_report_base_missing")
    # The disk report is untrusted after initial publication: it can be
    # replaced, corrupted, deleted, or redirected.  Rebuild from this deep
    # copied sanitized projection and atomically replace whatever is on disk.
    payload = deepcopy(base)
    payload["final_state"] = {
        "schema": "propextract.final-action.v1",
        "status": "done" if job.get("status") == "done" else "unknown",
        "published": job.get("published") is True,
        "workbook_sha256": target_hash,
        "summary": _safe_summary(job.get("summary")),
        "proposals": _safe_proposals(job.get("proposals")),
        "row_cards": _safe_row_cards(job.get("row_cards")),
        "actions": _safe_actions(job.get("action_events_internal")),
        "warning": _safe_warning(job.get("warning")),
    }
    return payload


def new_row_final_report_snapshot(state: ImportedNewRowState, payload: NewRowPayload) -> dict[str, object]:
    """Return detached memory-only final state; never touches report storage."""
    if type(state) is not ImportedNewRowState or type(payload) is not NewRowPayload:
        raise NewRowPayloadError("new_row_report_snapshot_invalid")
    if (state.action_id, state.construction_id, state.canonical_rns, state.object_tail) != (
        payload.action_id, payload.construction_id, payload.canonical_rns, payload.object_tail,
    ):
        raise NewRowPayloadError("new_row_report_snapshot_conflict")
    result = {
        "schema": "propextract.new-row-payload-snapshot.v1", "action_id": payload.action_id,
        "construction_id": payload.construction_id, "canonical_rns": payload.canonical_rns,
        "object_tail": payload.object_tail, "payload_digest": payload.digest,
        "fields": [[column, strict_json(value)] for column, value in sorted(payload.fields.items()) if column != 23],
        "w_display": payload.w_display,
        "imported_summary": strict_json(state.report_state),
    }
    # Canonical round trip is a cheap proof that this is detached JSON data.
    import json
    return json.loads(canonical_json(result))


def new_row_final_report_builder(state: ImportedNewRowState, payload: NewRowPayload):
    """Build compatible finalizer callback without filesystem authority."""
    def build(operation_id: str, target_row: int, post_hash: str) -> dict[str, object]:
        if operation_id != payload.action_id or type(target_row) is not int or target_row < 2 or type(post_hash) is not str or len(post_hash) != 64:
            raise NewRowPayloadError("new_row_report_snapshot_blocked")
        snapshot = new_row_final_report_snapshot(state, payload)
        snapshot["final_state"] = {"workbook_sha256": post_hash, "target_row": target_row}
        return snapshot
    return build


def write_final_action_report(target: Path, job: dict[str, object]) -> Path:
    """Atomically rebuild a final report from server-held safe state only."""
    path = report_path(target)
    atomic_json(path, final_report_payload(job))
    return path
