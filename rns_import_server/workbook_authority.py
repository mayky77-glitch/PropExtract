"""Durable, explicit authority for read-only workbook projections.

This boundary never discovers a workbook.  Callers enroll all identities and
evidence once; readers only reconstruct that exact durable tuple.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage, utc_now
from rns_import_server.workbook_projection import (
    GroupOwnershipEvidence, TemplateCellEvidence, WorkbookProjectionAuthority,
)


class WorkbookAuthorityError(RegistryError):
    """Fail-closed durable-authority boundary error."""


def _canonical_path(value: object) -> str:
    if type(value) is not str or not value or not os.path.isabs(value) or os.path.normpath(value) != value:
        raise WorkbookAuthorityError("workbook_authority_target_invalid")
    path = Path(value)
    try:
        if not path.is_file() or path.is_symlink() or str(path.resolve(strict=True)) != value:
            raise WorkbookAuthorityError("workbook_authority_target_invalid")
        for component in (path, *path.parents):
            if component.is_symlink():
                raise WorkbookAuthorityError("workbook_authority_target_invalid")
    except OSError as error:
        raise WorkbookAuthorityError("workbook_authority_target_invalid") from error
    return value


def _nonempty(value: object) -> str:
    if type(value) is not str or not value:
        raise WorkbookAuthorityError("workbook_authority_invalid")
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise WorkbookAuthorityError("workbook_authority_invalid")
    return value


def _json_value(value: object) -> bool:
    return value is None or type(value) in (bool, int, str) or (type(value) is float and math.isfinite(value))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _strict_json(value: str) -> object:
    def no_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=no_duplicate_pairs)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _template_payload(
    evidence: object, *, required_row: int | None = None,
) -> tuple[tuple[TemplateCellEvidence, ...], str, str]:
    if type(evidence) is not tuple or len(evidence) != 24:
        raise WorkbookAuthorityError("workbook_authority_template_invalid")
    cells: list[TemplateCellEvidence] = []
    for column, item in enumerate(evidence, 1):
        if (type(item) is not TemplateCellEvidence or type(item.row) is not int or type(item.column) is not int
                or item.row < 1 or (required_row is not None and item.row != required_row)
                or item.column != column or not _json_value(item.value)):
            raise WorkbookAuthorityError("workbook_authority_template_invalid")
        cells.append(item)
    payload = _canonical_json([{"row": item.row, "column": item.column, "value": item.value} for item in cells])
    return tuple(cells), payload, _digest(payload)


def _ownership_payload(evidence: object, max_row: object) -> tuple[tuple[GroupOwnershipEvidence, ...], str, str]:
    if type(max_row) is not int or max_row < 1 or type(evidence) is not tuple or len(evidence) != max_row:
        raise WorkbookAuthorityError("workbook_authority_ownership_invalid")
    rows: list[GroupOwnershipEvidence] = []
    for number, item in enumerate(evidence, 1):
        if type(item) is not GroupOwnershipEvidence or type(item.row) is not int or item.row != number or type(item.owned) is not bool:
            raise WorkbookAuthorityError("workbook_authority_ownership_invalid")
        rows.append(item)
    payload = _canonical_json([{"row": item.row, "owned": item.owned} for item in rows])
    return tuple(rows), payload, _digest(payload)


@dataclass(frozen=True)
class WorkbookAuthorityEnrollment:
    action_id: str
    construction_id: str
    workbook_contract_id: str
    target_identity: str
    target_path: str
    sheet_identity: str
    template_version: str
    source_sha256: str
    template_cells: tuple[TemplateCellEvidence, ...]
    group_ownership: tuple[GroupOwnershipEvidence, ...]
    max_row: int


class WorkbookAuthorityStore:
    """Strict insert-or-exact-replay authority enrollment."""

    def __init__(self, storage: RegistryStorage):
        self.storage = storage

    def enroll(self, enrollment: WorkbookAuthorityEnrollment) -> None:
        if type(enrollment) is not WorkbookAuthorityEnrollment:
            raise WorkbookAuthorityError("workbook_authority_invalid")
        action_id = _nonempty(enrollment.action_id)
        values = tuple(_nonempty(value) for value in (
            enrollment.construction_id, enrollment.workbook_contract_id, enrollment.target_identity,
            enrollment.sheet_identity, enrollment.template_version,
        ))
        target_path = _canonical_path(enrollment.target_path)
        source_sha256 = _sha256(enrollment.source_sha256)
        template_cells, template_json, template_digest = _template_payload(enrollment.template_cells, required_row=3)
        ownership, ownership_json, ownership_digest = _ownership_payload(enrollment.group_ownership, enrollment.max_row)
        try:
            with self.storage.transaction() as connection:
                action = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)).fetchone()
                if action is None or tuple(action[key] for key in ("construction_id", "workbook_contract_id", "target_identity", "target_path")) != (
                    values[0], values[1], values[2], target_path
                ):
                    raise WorkbookAuthorityError("workbook_authority_action_invalid")
                existing = connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (action_id,)).fetchone()
                stable = (values[0], values[1], values[2], target_path, values[3], values[4], source_sha256,
                          template_json, template_digest, 24, ownership_json, ownership_digest, len(ownership), enrollment.max_row)
                if existing is not None:
                    actual = tuple(existing[key] for key in (
                        "construction_id", "workbook_contract_id", "target_identity", "target_path", "sheet_identity",
                        "template_version", "source_sha256", "template_evidence", "template_digest", "template_count",
                        "ownership_evidence", "ownership_digest", "ownership_count", "max_row",
                    ))
                    if actual != stable:
                        raise RegistryConflictError("workbook_authority_conflict")
                    self._decode(existing)
                    return
                generation = int(connection.execute("SELECT generation FROM registry_meta WHERE id=1").fetchone()[0]) + 1
                connection.execute(
                    """INSERT INTO workbook_authorities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (action_id, *stable, generation, utc_now()),
                )
                self.storage._increment_generation(connection)
        except WorkbookAuthorityError:
            raise
        except sqlite3.Error as error:
            raise WorkbookAuthorityError("workbook_authority_storage_failed") from error

    register = enroll

    @staticmethod
    def _decode(row: sqlite3.Row) -> WorkbookProjectionAuthority:
        try:
            required = ("action_id", "construction_id", "workbook_contract_id", "target_identity", "target_path", "sheet_identity",
                        "template_version", "source_sha256", "template_evidence", "template_digest", "template_count",
                        "ownership_evidence", "ownership_digest", "ownership_count", "max_row", "registry_generation")
            if any(key not in row.keys() for key in required):
                raise ValueError
            _nonempty(row["action_id"]); _nonempty(row["construction_id"]); _nonempty(row["workbook_contract_id"])
            _nonempty(row["target_identity"]); _canonical_path(row["target_path"]); _nonempty(row["sheet_identity"])
            _nonempty(row["template_version"]); _sha256(row["source_sha256"])
            if type(row["template_count"]) is not int or row["template_count"] != 24 or type(row["ownership_count"]) is not int:
                raise ValueError
            template_raw = _strict_json(row["template_evidence"])
            ownership_raw = _strict_json(row["ownership_evidence"])
            if _canonical_json(template_raw) != row["template_evidence"] or _digest(row["template_evidence"]) != _sha256(row["template_digest"]):
                raise ValueError
            if _canonical_json(ownership_raw) != row["ownership_evidence"] or _digest(row["ownership_evidence"]) != _sha256(row["ownership_digest"]):
                raise ValueError
            template = tuple(TemplateCellEvidence(**item) for item in template_raw)
            ownership = tuple(GroupOwnershipEvidence(**item) for item in ownership_raw)
            max_row = row["max_row"]
            template, _, _ = _template_payload(template)
            ownership, _, _ = _ownership_payload(ownership, max_row)
            if row["ownership_count"] != len(ownership) or type(row["registry_generation"]) is not int or row["registry_generation"] < 0:
                raise ValueError
            return WorkbookProjectionAuthority.verified(
                target_path=row["target_path"], target_identity=row["target_identity"],
                workbook_contract_id=row["workbook_contract_id"], sheet_identity=row["sheet_identity"],
                template_version=row["template_version"], registry_generation=row["registry_generation"],
                expected_source_sha256=row["source_sha256"], template_cells=template, group_ownership=ownership,
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, WorkbookAuthorityError) as error:
            raise WorkbookAuthorityError("workbook_authority_corrupt") from error


class RegistryWorkbookProjectionAuthority:
    """Concrete read-only ``WorkbookProjectionAuthorityPort`` producer."""

    def __init__(self, storage: RegistryStorage, action_id: str):
        self.storage = storage
        self.action_id = action_id

    def read_authority(self) -> WorkbookProjectionAuthority:
        if type(self.action_id) is not str or not self.action_id:
            raise WorkbookAuthorityError("workbook_authority_action_invalid")
        begun = False
        try:
            self.storage.connection.execute("BEGIN")
            begun = True
            generation = int(self.storage.connection.execute("SELECT generation FROM registry_meta WHERE id=1").fetchone()[0])
            action = self.storage.connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (self.action_id,)).fetchone()
            authority = self.storage.connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (self.action_id,)).fetchone()
            if action is None or authority is None or action["state"] != "pending":
                raise WorkbookAuthorityError("workbook_authority_missing")
            decoded = WorkbookAuthorityStore._decode(authority)
            if authority["registry_generation"] != generation or tuple(action[key] for key in (
                "construction_id", "workbook_contract_id", "target_identity", "target_path"
            )) != tuple(authority[key] for key in ("construction_id", "workbook_contract_id", "target_identity", "target_path")):
                raise WorkbookAuthorityError("workbook_authority_tuple_invalid")
            bindings = self.storage.connection.execute(
                "SELECT * FROM construction_bindings WHERE construction_id=? ORDER BY id", (action["construction_id"],)
            ).fetchall()
            if bindings and (len(bindings) != 1 or tuple(bindings[0][key] for key in (
                "workbook_contract_id", "target_identity", "sheet_identity", "template_version", "verified_state"
            )) != (authority["workbook_contract_id"], authority["target_identity"], authority["sheet_identity"], authority["template_version"], "verified")):
                raise WorkbookAuthorityError("workbook_authority_binding_invalid")
            self.storage.connection.execute("COMMIT")
            begun = False
            return decoded
        except WorkbookAuthorityError:
            if begun:
                self.storage.connection.execute("ROLLBACK")
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            if begun:
                self.storage.connection.execute("ROLLBACK")
            raise WorkbookAuthorityError("workbook_authority_storage_failed") from error
