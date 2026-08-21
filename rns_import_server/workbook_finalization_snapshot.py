"""Strict, durable input for post-publication finalization.

This module contains no finalizer.  It only canonicalizes the server-held
report projection that becomes authority before an XLSX replacement.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from rns_import_server.report_sanitization import safe_report_projection

SNAPSHOT_VERSION = 1
MAX_CANONICAL_PAYLOAD_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")


class FinalizationSnapshotError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical_json(value: object, *, enforce_size: bool = True) -> str:
    def check(item: object) -> None:
        if item is None or type(item) in {str, bool}:
            return
        if type(item) is int:
            return
        if type(item) is float:
            if math.isfinite(item):
                return
            raise FinalizationSnapshotError("finalization_snapshot_invalid")
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict:
            for key, child in item.items():
                if not isinstance(key, str):
                    raise FinalizationSnapshotError("finalization_snapshot_invalid")
                check(child)
            return
        raise FinalizationSnapshotError("finalization_snapshot_invalid")

    check(value)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if enforce_size and len(encoded.encode("utf-8")) > MAX_CANONICAL_PAYLOAD_BYTES:
        raise FinalizationSnapshotError("finalization_snapshot_too_large")
    return encoded


def build_payload(*, action_id: str, target_row: int, report: object) -> dict[str, object]:
    if type(action_id) is not str or not action_id or type(target_row) is not int or target_row < 2:
        raise FinalizationSnapshotError("finalization_snapshot_invalid")
    # The report builder is an authority boundary.  Do not let a mapping/list
    # proxy, bytes, subclasses, or non-finite number reach the permissive
    # report projector and become a different value.
    canonical_json(report, enforce_size=False)
    projected = safe_report_projection(report)
    if type(projected) is not dict:
        raise FinalizationSnapshotError("finalization_snapshot_invalid")
    return {"action_id": action_id, "target_row": target_row, "report_payload": projected}


def validate_payload(
    *, operation_id: str, consumer_id: object, workbook_contract_id: object, post_hash: str, payload: object,
) -> tuple[str, str]:
    if type(operation_id) is not str or not operation_id or consumer_id != operation_id:
        raise FinalizationSnapshotError("consumer_action_identity_mismatch")
    if type(workbook_contract_id) is not str or not workbook_contract_id.strip():
        raise FinalizationSnapshotError("workbook_contract_id_required")
    if type(post_hash) is not str or not _SHA256.fullmatch(post_hash):
        raise FinalizationSnapshotError("finalization_snapshot_invalid")
    if type(payload) is not dict or set(payload) != {"action_id", "target_row", "report_payload"}:
        raise FinalizationSnapshotError("finalization_snapshot_invalid")
    if payload["action_id"] != operation_id or type(payload["target_row"]) is not int or payload["target_row"] < 2:
        raise FinalizationSnapshotError("finalization_snapshot_invalid")
    report = payload["report_payload"]
    if type(report) is not dict:
        raise FinalizationSnapshotError("finalization_snapshot_invalid")
    final_state = report.get("final_state")
    if type(final_state) is not dict or final_state.get("workbook_sha256") != post_hash:
        raise FinalizationSnapshotError("finalization_snapshot_invalid")
    canonical = canonical_json(payload)
    envelope = canonical_json({"operation_id": operation_id, "snapshot_version": SNAPSHOT_VERSION, "payload": payload}, enforce_size=False)
    return canonical, hashlib.sha256(envelope.encode("utf-8")).hexdigest()


def verify_snapshot(
    *, operation_id: str, consumer_id: object, workbook_contract_id: object, post_hash: object,
    snapshot_version: object, canonical_payload: object, digest: object,
) -> bool:
    if snapshot_version != SNAPSHOT_VERSION or not isinstance(canonical_payload, str) or not isinstance(digest, str):
        return False
    try:
        payload: Any = json.loads(canonical_payload)
        normalized, expected_digest = validate_payload(
            operation_id=operation_id, consumer_id=consumer_id, workbook_contract_id=workbook_contract_id,
            post_hash=post_hash, payload=payload,
        )
        if normalized != canonical_payload:
            return False
    except (json.JSONDecodeError, FinalizationSnapshotError):
        return False
    return expected_digest == digest
