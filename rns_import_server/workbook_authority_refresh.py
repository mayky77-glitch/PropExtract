"""Atomic durable refresh of one enrolled workbook authority.

This module deliberately has no workbook writer, native adapter, finalizer, or
server dependency.  It consumes already-published journal/snapshot evidence
and only replaces the durable projection authority plus an immutable receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sqlite3
from typing import Any, Literal, Mapping

from rns_import_server.registry_storage import RegistryStorage, utc_now
from rns_import_server.workbook_finalization_snapshot import verify_snapshot


_RECEIPT_VERSION = 1
_MANIFEST_VERSION = "group-row-manifest-v3"
_AUTHORITY_FIELDS = (
    "action_id", "construction_id", "workbook_contract_id", "target_identity", "target_path",
    "sheet_identity", "template_version", "source_sha256", "template_evidence", "template_digest",
    "template_count", "ownership_evidence", "ownership_digest", "ownership_count", "max_row",
    "registry_generation", "created_at",
)
_SHA_FIELDS = frozenset({"source_sha256", "template_digest", "ownership_digest"})
_PENDING_CODES = frozenset({"refresh_target_unreadable", "refresh_target_unstable", "refresh_sqlite_failed"})


class AuthorityRefreshError(RuntimeError):
    """A fail-closed verifier error with a stable, non-sensitive code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AuthorityRefreshResult:
    operation_id: str
    status: Literal["refreshed", "replayed", "published_pending_finalization", "manual_repair"]
    error_code: str | None = None
    prior_generation: int | None = None
    successor_generation: int | None = None


@dataclass(frozen=True)
class AuthorityRefreshReceipt:
    operation_id: str
    action_id: str
    receipt_version: int
    manifest_version: str
    mutation_mode: Literal["blank_fill", "middle_insert"]
    target_row: int
    pre_hash: str
    post_hash: str
    prior_generation: int
    successor_generation: int
    predecessor_digest: str
    successor_digest: str
    envelope_digest: str
    created_at: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _canonical_authority_json(value: object) -> str:
    """Retain WA1's insertion-ordered evidence encoding exactly."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _strict_json(value: object) -> object:
    if not isinstance(value, str):
        raise AuthorityRefreshError("refresh_receipt_corrupt")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    try:
        return json.loads(value, object_pairs_hook=reject_duplicates)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise AuthorityRefreshError("refresh_receipt_corrupt") from error


def _digest(domain: str, canonical: str) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + canonical.encode("utf-8")).hexdigest()


def _sha256(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise AuthorityRefreshError("refresh_authority_corrupt")
    return value


def _nonempty(value: object, code: str = "refresh_authority_corrupt") -> str:
    if type(value) is not str or not value:
        raise AuthorityRefreshError(code)
    return value


def _wa1_scalar(value: object) -> bool:
    return value is None or type(value) in {bool, int, str} or (type(value) is float and math.isfinite(value))


def _target_parts(value: object) -> tuple[Path, tuple[str, ...]]:
    if type(value) is not str or not value or not os.path.isabs(value) or os.path.normpath(value) != value:
        raise AuthorityRefreshError("refresh_target_unreadable")
    path = Path(value)
    if path.anchor != os.path.sep or not path.parts[1:] or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise AuthorityRefreshError("refresh_target_unreadable")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise AuthorityRefreshError("refresh_target_unreadable")
    return path, tuple(path.parts[1:])


def _bound_sha256(value: object) -> str:
    path, parts = _target_parts(value)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    try:
        root = os.open(path.anchor, directory_flags)
        descriptors.append(root)
        for component in parts[:-1]:
            descriptor = os.open(component, directory_flags, dir_fd=descriptors[-1])
            descriptors.append(descriptor)
        descriptor = os.open(parts[-1], file_flags, dir_fd=descriptors[-1])
    except OSError as error:
        for open_descriptor in reversed(descriptors):
            os.close(open_descriptor)
        raise AuthorityRefreshError("refresh_target_unreadable") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AuthorityRefreshError("refresh_target_unreadable")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        if after != before:
            raise AuthorityRefreshError("refresh_target_unstable")
        # Every component was opened relative to a held parent descriptor.
        # Bind that chain back to the canonical absolute names after reading;
        # a swapped ancestor/symlink therefore fails without touching its
        # replacement bytes.
        current_path = Path(path.anchor)
        for component, open_descriptor in zip(parts[:-1], descriptors[1:]):
            current_path /= component
            current = os.lstat(current_path)
            held = os.fstat(open_descriptor)
            if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise AuthorityRefreshError("refresh_target_unstable")
        current = os.lstat(path)
        if (stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)):
            raise AuthorityRefreshError("refresh_target_unstable")
        return digest.hexdigest()
    except OSError as error:
        raise AuthorityRefreshError("refresh_target_unreadable") from error
    finally:
        os.close(descriptor)
        for open_descriptor in reversed(descriptors):
            os.close(open_descriptor)


def _authority_payload(row: Mapping[str, object], *, require_wa1_template: bool = False) -> dict[str, object]:
    try:
        if set(_AUTHORITY_FIELDS) - set(row.keys()):
            raise ValueError
        payload = {name: row[name] for name in _AUTHORITY_FIELDS}
        for name in ("action_id", "construction_id", "workbook_contract_id", "target_identity", "target_path",
                     "sheet_identity", "template_version", "template_evidence", "ownership_evidence", "created_at"):
            _nonempty(payload[name])
        for name in _SHA_FIELDS:
            _sha256(payload[name])
        if (type(payload["template_count"]) is not int or payload["template_count"] != 24
                or type(payload["ownership_count"]) is not int or payload["ownership_count"] < 1
                or type(payload["max_row"]) is not int or payload["max_row"] < 1
                or type(payload["registry_generation"]) is not int or payload["registry_generation"] < 0):
            raise ValueError
        template = _strict_json(payload["template_evidence"])
        ownership = _strict_json(payload["ownership_evidence"])
        if not isinstance(template, list) or not isinstance(ownership, list):
            raise ValueError
        if (_canonical_authority_json(template) != payload["template_evidence"]
                or _canonical_authority_json(ownership) != payload["ownership_evidence"]):
            raise ValueError
        # WA1's durable digests are intentionally undomained.  Preserve that
        # exact storage contract while domain-separating the new receipt only.
        if hashlib.sha256(payload["template_evidence"].encode("utf-8")).hexdigest() != payload["template_digest"]:
            raise ValueError
        if hashlib.sha256(payload["ownership_evidence"].encode("utf-8")).hexdigest() != payload["ownership_digest"]:
            raise ValueError
        if len(template) != 24 or len(ownership) != payload["ownership_count"] or len(ownership) != payload["max_row"]:
            raise ValueError
        for column, item in enumerate(template, 1):
            if (not isinstance(item, dict) or set(item) != {"row", "column", "value"}
                    or type(item["row"]) is not int or type(item["column"]) is not int
                    or (require_wa1_template and item["row"] != 3) or item["column"] != column
                    or not _wa1_scalar(item["value"])):
                raise ValueError
        for number, item in enumerate(ownership, 1):
            if (not isinstance(item, dict) or set(item) != {"row", "owned"}
                    or type(item["row"]) is not int or type(item["owned"]) is not bool or item["row"] != number):
                raise ValueError
        return payload
    except (AuthorityRefreshError, TypeError, ValueError, KeyError):
        raise AuthorityRefreshError("refresh_authority_corrupt")


def _successor(predecessor: Mapping[str, object], *, mutation_mode: str, target_row: int,
               post_hash: str, successor_generation: int) -> dict[str, object]:
    result = dict(predecessor)
    ownership = _strict_json(predecessor["ownership_evidence"])
    template = _strict_json(predecessor["template_evidence"])
    if not isinstance(ownership, list) or not isinstance(template, list):
        raise AuthorityRefreshError("refresh_receipt_corrupt")
    max_row = predecessor["max_row"]
    if type(max_row) is not int:
        raise AuthorityRefreshError("refresh_receipt_corrupt")
    if mutation_mode == "blank_fill":
        if not 2 <= target_row <= max_row or ownership[target_row - 1]["owned"]:
            raise AuthorityRefreshError("refresh_mapping_invalid")
        ownership[target_row - 1] = {"row": target_row, "owned": True}
    elif mutation_mode == "middle_insert":
        if not 2 <= target_row <= max_row + 1:
            raise AuthorityRefreshError("refresh_mapping_invalid")
        ownership = [
            {"row": item["row"] + 1 if item["row"] >= target_row else item["row"], "owned": item["owned"]}
            for item in ownership
        ]
        ownership.insert(target_row - 1, {"row": target_row, "owned": True})
        template = [
            {"row": item["row"] + 1 if item["row"] >= target_row else item["row"], "column": item["column"], "value": item["value"]}
            for item in template
        ]
        result["max_row"] = max_row + 1
        result["ownership_count"] = max_row + 1
    else:
        raise AuthorityRefreshError("refresh_mapping_invalid")
    result["ownership_evidence"] = _canonical_authority_json(ownership)
    result["ownership_digest"] = hashlib.sha256(result["ownership_evidence"].encode("utf-8")).hexdigest()
    result["template_evidence"] = _canonical_authority_json(template)
    result["template_digest"] = hashlib.sha256(result["template_evidence"].encode("utf-8")).hexdigest()
    result["source_sha256"] = post_hash
    result["registry_generation"] = successor_generation
    return _authority_payload(result)


def _receipt_envelope(row: Mapping[str, object]) -> dict[str, object]:
    return {name: row[name] for name in (
        "operation_id", "action_id", "receipt_version", "manifest_version", "mutation_mode", "target_row", "pre_hash",
        "post_hash", "prior_generation", "successor_generation", "predecessor_digest", "successor_digest", "created_at",
    )}


def _receipt(row: Mapping[str, object]) -> AuthorityRefreshReceipt:
    try:
        if {"operation_id", "action_id", "receipt_version", "manifest_version", "mutation_mode", "target_row",
            "pre_hash", "post_hash", "prior_generation", "successor_generation", "predecessor_payload",
            "predecessor_digest", "successor_payload", "successor_digest", "envelope_digest", "created_at"} - set(row.keys()):
            raise ValueError
        if row["receipt_version"] != _RECEIPT_VERSION or row["manifest_version"] != _MANIFEST_VERSION:
            raise ValueError
        if row["mutation_mode"] not in {"blank_fill", "middle_insert"} or type(row["target_row"]) is not int or row["target_row"] < 2:
            raise ValueError
        for name in ("operation_id", "action_id", "created_at"):
            _nonempty(row[name], "refresh_receipt_corrupt")
        for name in ("pre_hash", "post_hash", "predecessor_digest", "successor_digest", "envelope_digest"):
            _sha256(row[name])
        if (type(row["prior_generation"]) is not int or type(row["successor_generation"]) is not int
                or row["prior_generation"] < 0 or row["successor_generation"] != row["prior_generation"] + 1):
            raise ValueError
        predecessor = _strict_json(row["predecessor_payload"])
        successor = _strict_json(row["successor_payload"])
        if not isinstance(predecessor, dict) or not isinstance(successor, dict):
            raise ValueError
        predecessor_json = _canonical_json(predecessor)
        successor_json = _canonical_json(successor)
        if predecessor_json != row["predecessor_payload"] or successor_json != row["successor_payload"]:
            raise ValueError
        if (_digest("workbook-authority-refresh-predecessor-v1", predecessor_json) != row["predecessor_digest"]
                or _digest("workbook-authority-refresh-successor-v1", successor_json) != row["successor_digest"]):
            raise ValueError
        if _digest("workbook-authority-refresh-receipt-v1", _canonical_json(_receipt_envelope(row))) != row["envelope_digest"]:
            raise ValueError
        return AuthorityRefreshReceipt(
            operation_id=row["operation_id"], action_id=row["action_id"], receipt_version=row["receipt_version"],
            manifest_version=row["manifest_version"], mutation_mode=row["mutation_mode"], target_row=row["target_row"],
            pre_hash=row["pre_hash"], post_hash=row["post_hash"], prior_generation=row["prior_generation"],
            successor_generation=row["successor_generation"], predecessor_digest=row["predecessor_digest"],
            successor_digest=row["successor_digest"], envelope_digest=row["envelope_digest"], created_at=row["created_at"],
        )
    except (AuthorityRefreshError, TypeError, ValueError, KeyError):
        raise AuthorityRefreshError("refresh_receipt_corrupt")


def _same_authority(row: Mapping[str, object], payload: Mapping[str, object]) -> bool:
    return all(row[name] == payload[name] for name in _AUTHORITY_FIELDS)


def _read_context(connection: sqlite3.Connection, operation_id: str) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row, sqlite3.Row]:
    journal = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
    action = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (operation_id,)).fetchone()
    authority_rows = connection.execute("SELECT * FROM workbook_authorities ORDER BY action_id").fetchall()
    snapshot = connection.execute("SELECT * FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,)).fetchone()
    if journal is None or action is None or snapshot is None or len(authority_rows) != 1:
        raise AuthorityRefreshError("refresh_evidence_missing")
    return journal, action, authority_rows[0], snapshot


def _validate_first_context(connection: sqlite3.Connection, journal: sqlite3.Row, action: sqlite3.Row,
                            authority: sqlite3.Row, snapshot: sqlite3.Row, operation_id: str) -> tuple[dict[str, object], int]:
    predecessor = _authority_payload(authority, require_wa1_template=True)
    try:
        if (journal["operation_id"] != operation_id or journal["consumer_id"] != operation_id
                or authority["action_id"] != operation_id or action["action_id"] != operation_id
                or journal["operation_kind"] != "new_row" or journal["phase"] != "published"
                or journal["manifest_version"] != _MANIFEST_VERSION or journal["mutation_mode"] not in {"blank_fill", "middle_insert"}
                or action["state"] != "pending"):
            raise ValueError
        for name in ("construction_id", "workbook_contract_id", "target_identity"):
            if journal[name] != action[name] or authority[name] != action[name]:
                raise ValueError
        for name in ("workbook_contract_id", "target_identity", "sheet_identity", "template_version"):
            if authority[name] != journal[name]:
                raise ValueError
        if authority["target_path"] != action["target_path"]:
            raise ValueError
        if predecessor["source_sha256"] != journal["pre_hash"] or not verify_snapshot(
            operation_id=operation_id, consumer_id=journal["consumer_id"], workbook_contract_id=journal["workbook_contract_id"],
            post_hash=journal["post_hash"], snapshot_version=snapshot["snapshot_version"],
            canonical_payload=snapshot["canonical_payload"], digest=snapshot["digest"],
        ):
            raise ValueError
        payload = _strict_json(snapshot["canonical_payload"])
        if not isinstance(payload, dict) or type(payload.get("target_row")) is not int:
            raise ValueError
        generation = authority["registry_generation"]
        current_generation = connection.execute("SELECT generation FROM registry_meta WHERE id=1").fetchone()[0]
        if type(generation) is not int or journal["expected_generation"] != generation or current_generation != generation:
            raise ValueError
        return predecessor, payload["target_row"]
    except (AuthorityRefreshError, TypeError, ValueError, KeyError):
        raise AuthorityRefreshError("refresh_evidence_contradictory")


def _validate_replay_context(connection: sqlite3.Connection, *, operation_id: str, receipt: AuthorityRefreshReceipt,
                             predecessor: Mapping[str, object], successor: Mapping[str, object], journal: sqlite3.Row,
                             action: sqlite3.Row, authority: sqlite3.Row, snapshot: sqlite3.Row) -> None:
    """Bind every replay input to the immutable receipt before accepting it."""
    try:
        if (receipt.operation_id != operation_id or receipt.action_id != operation_id
                or predecessor["action_id"] != operation_id or successor["action_id"] != operation_id
                or predecessor["source_sha256"] != receipt.pre_hash or predecessor["registry_generation"] != receipt.prior_generation
                or successor["source_sha256"] != receipt.post_hash or successor["registry_generation"] != receipt.successor_generation
                or journal["operation_id"] != operation_id or journal["consumer_id"] != operation_id
                or journal["operation_kind"] != "new_row" or journal["phase"] != "published"
                or journal["manifest_version"] != _MANIFEST_VERSION or journal["manifest_version"] != receipt.manifest_version
                or journal["mutation_mode"] != receipt.mutation_mode or journal["pre_hash"] != receipt.pre_hash
                or journal["post_hash"] != receipt.post_hash or journal["expected_generation"] != receipt.prior_generation
                or action["action_id"] != operation_id or action["state"] != "pending" or not _same_authority(authority, successor)):
            raise ValueError
        for name in ("construction_id", "workbook_contract_id", "target_identity", "target_path", "sheet_identity", "template_version"):
            if predecessor[name] != successor[name]:
                raise ValueError
        for name in ("construction_id", "workbook_contract_id", "target_identity", "target_path"):
            if predecessor[name] != action[name]:
                raise ValueError
        for name in ("construction_id", "workbook_contract_id", "target_identity", "sheet_identity", "template_version"):
            if predecessor[name] != journal[name]:
                raise ValueError
        if not verify_snapshot(operation_id=operation_id, consumer_id=journal["consumer_id"],
                               workbook_contract_id=journal["workbook_contract_id"], post_hash=journal["post_hash"],
                               snapshot_version=snapshot["snapshot_version"], canonical_payload=snapshot["canonical_payload"],
                               digest=snapshot["digest"]):
            raise ValueError
        snapshot_payload = _strict_json(snapshot["canonical_payload"])
        if not isinstance(snapshot_payload, dict) or snapshot_payload.get("target_row") != receipt.target_row:
            raise ValueError
        rebuilt = _successor(predecessor, mutation_mode=receipt.mutation_mode, target_row=receipt.target_row,
                             post_hash=receipt.post_hash, successor_generation=receipt.successor_generation)
        if rebuilt != successor or connection.execute("SELECT generation FROM registry_meta WHERE id=1").fetchone()[0] != receipt.successor_generation:
            raise ValueError
    except (AuthorityRefreshError, TypeError, ValueError, KeyError):
        raise AuthorityRefreshError("refresh_evidence_contradictory")


def _verify_existing(storage: RegistryStorage, operation_id: str, *, within_transaction: bool = False) -> AuthorityRefreshReceipt:
    connection = storage.connection
    row = connection.execute("SELECT * FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation_id,)).fetchone()
    if row is None:
        raise AuthorityRefreshError("refresh_receipt_missing")
    receipt = _receipt(row)
    if receipt.operation_id != operation_id or receipt.action_id != operation_id:
        raise AuthorityRefreshError("refresh_receipt_corrupt")
    journal, action, authority, snapshot = _read_context(connection, operation_id)
    predecessor = _authority_payload(_strict_json(row["predecessor_payload"]), require_wa1_template=True)
    stored_successor = _authority_payload(_strict_json(row["successor_payload"]))
    _validate_replay_context(connection, operation_id=operation_id, receipt=receipt, predecessor=predecessor,
                             successor=stored_successor, journal=journal, action=action, authority=authority, snapshot=snapshot)
    if _bound_sha256(action["target_path"]) != receipt.post_hash:
        raise AuthorityRefreshError("refresh_target_hash_mismatch")
    return receipt


def verify_authority_refresh_receipt(storage: RegistryStorage, operation_id: str) -> AuthorityRefreshReceipt:
    """Validate and project one receipt without exposing authority payloads."""
    if not isinstance(storage, RegistryStorage) or type(operation_id) is not str or not operation_id:
        raise AuthorityRefreshError("refresh_operation_invalid")
    begun = False
    try:
        storage.connection.execute("BEGIN")
        begun = True
        receipt = _verify_existing(storage, operation_id, within_transaction=True)
        storage.connection.execute("COMMIT")
        begun = False
        return receipt
    except Exception:
        if begun:
            storage.connection.execute("ROLLBACK")
        raise


def _result(operation_id: str, status: Literal["published_pending_finalization", "manual_repair"], code: str) -> AuthorityRefreshResult:
    return AuthorityRefreshResult(operation_id=operation_id, status=status, error_code=code)


def refresh_published_authority(storage: RegistryStorage, operation_id: str) -> AuthorityRefreshResult:
    """Atomically refresh a published WA1 authority, or return a typed safe state."""
    if not isinstance(storage, RegistryStorage) or type(operation_id) is not str or not operation_id:
        return _result(operation_id if type(operation_id) is str else "", "manual_repair", "refresh_operation_invalid")
    begun = False
    try:
        storage.connection.execute("BEGIN IMMEDIATE")
        begun = True
        existing = storage.connection.execute(
            "SELECT 1 FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if existing is not None:
            receipt = _verify_existing(storage, operation_id, within_transaction=True)
            storage.connection.execute("COMMIT")
            begun = False
            return AuthorityRefreshResult(operation_id, "replayed", prior_generation=receipt.prior_generation,
                                          successor_generation=receipt.successor_generation)
        journal, action, authority, snapshot = _read_context(storage.connection, operation_id)
        predecessor, target_row = _validate_first_context(storage.connection, journal, action, authority, snapshot, operation_id)
        if _bound_sha256(action["target_path"]) != journal["post_hash"]:
            raise AuthorityRefreshError("refresh_target_hash_mismatch")
        prior_generation = predecessor["registry_generation"]
        assert type(prior_generation) is int
        successor_generation = prior_generation + 1
        successor = _successor(predecessor, mutation_mode=journal["mutation_mode"], target_row=target_row,
                               post_hash=journal["post_hash"], successor_generation=successor_generation)
        predecessor_json = _canonical_json(predecessor)
        successor_json = _canonical_json(successor)
        now = utc_now()
        receipt_values: dict[str, object] = {
            "operation_id": operation_id, "action_id": operation_id, "receipt_version": _RECEIPT_VERSION,
            "manifest_version": _MANIFEST_VERSION, "mutation_mode": journal["mutation_mode"], "target_row": target_row,
            "pre_hash": journal["pre_hash"], "post_hash": journal["post_hash"], "prior_generation": prior_generation,
            "successor_generation": successor_generation,
            "predecessor_payload": predecessor_json,
            "predecessor_digest": _digest("workbook-authority-refresh-predecessor-v1", predecessor_json),
            "successor_payload": successor_json,
            "successor_digest": _digest("workbook-authority-refresh-successor-v1", successor_json), "created_at": now,
        }
        receipt_values["envelope_digest"] = _digest(
            "workbook-authority-refresh-receipt-v1", _canonical_json(_receipt_envelope(receipt_values))
        )
        storage.connection.execute(
            "UPDATE workbook_authorities SET source_sha256=?, template_evidence=?, template_digest=?, template_count=?, "
            "ownership_evidence=?, ownership_digest=?, ownership_count=?, max_row=?, registry_generation=? WHERE action_id=?",
            tuple(successor[name] for name in ("source_sha256", "template_evidence", "template_digest", "template_count",
                                                "ownership_evidence", "ownership_digest", "ownership_count", "max_row",
                                                "registry_generation")) + (operation_id,),
        )
        storage.connection.execute(
            "INSERT INTO workbook_authority_refresh_receipts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(receipt_values[name] for name in (
                "operation_id", "action_id", "receipt_version", "manifest_version", "mutation_mode", "target_row", "pre_hash",
                "post_hash", "prior_generation", "successor_generation", "predecessor_payload", "predecessor_digest",
                "successor_payload", "successor_digest", "envelope_digest", "created_at",
            )),
        )
        storage._increment_generation(storage.connection)
        storage.connection.execute("COMMIT")
        begun = False
        return AuthorityRefreshResult(operation_id, "refreshed", prior_generation=prior_generation,
                                      successor_generation=successor_generation)
    except AuthorityRefreshError as error:
        if begun:
            storage.connection.execute("ROLLBACK")
        return _result(operation_id, "published_pending_finalization" if error.code in _PENDING_CODES else "manual_repair", error.code)
    except sqlite3.Error:
        if begun:
            storage.connection.execute("ROLLBACK")
        return _result(operation_id, "published_pending_finalization", "refresh_sqlite_failed")
    except Exception:
        if begun:
            storage.connection.execute("ROLLBACK")
        return _result(operation_id, "manual_repair", "refresh_internal_invalid")
