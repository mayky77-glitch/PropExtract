"""Durable, fail-closed publisher for one resolved construction-group row."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Callable, Mapping, Protocol
from uuid import UUID, uuid4

from rns_import_server.audit import sha256
from rns_import_server.excel_native import NativeExcelError, NativeInsertRequest, native_excel_available, run_native_insert
from rns_import_server.opc_worksheet_x14_cf_insertion_oracle import (
    OPCWorksheetX14CfInsertionOracleError,
    validate_x14_cf_middle_insert,
)
from rns_import_server.opc_workbook_filter_database_insertion_oracle import (
    OPCWorkbookFilterDatabaseInsertionOracleError,
    validate_filter_database_middle_insert,
)
from rns_import_server.opc_worksheet_structure_insertion_oracle import (
    OPCWorksheetStructureInsertionOracleError,
    validate_worksheet_structure_middle_insert,
)
from rns_import_server.workbook_groups import MutationPlan
from rns_import_server.normalization import canonical_rns_identity
from rns_import_server.workbook_mutation_manifest import (
    MutationManifestError,
    manifest_for,
    validate_blank_fill,
    validate_control,
    validate_dependent_registry_references,
    validate_inserted_row,
    validate_insertion,
)
from rns_import_server.workbook_structure import inspect_workbook, insertion_is_structurally_safe
from rns_import_server.registry_storage import RegistryConflictError


class GroupRowInsertionError(RuntimeError):
    """Public recovery envelope retaining stage and original system failure."""
    def __init__(self, code: str, *, stage: str, cause: BaseException | None = None, cleanup: BaseException | None = None):
        self.code, self.stage, self.cause, self.cleanup = code, stage, cause, cleanup
        detail = f": {cause}" if cause else ""
        if cleanup:
            detail += f"; cleanup: {cleanup}"
        super().__init__(f"{code}@{stage}{detail}")


class Journal(Protocol):
    def get(self, operation_id: str) -> object | None: ...
    def reserve(self, *, nonce_factory: Callable[[], tuple[str, str]], **kwargs: object) -> tuple[object, bool]: ...
    def create(self, **kwargs: object) -> object: ...
    def transition(self, operation_id: str, *, expected_phase: str, next_phase: str, **kwargs: object) -> object: ...
    def record_post_hash(self, operation_id: str, *, expected_phase: str, post_hash: str) -> object: ...
    def finalize_flag(self, operation_id: str, flag: str) -> object: ...


@dataclass(frozen=True)
class PublicationContext:
    """Integration-owned authority; callers cannot skip lock/re-resolution."""
    lock: Callable[[], AbstractContextManager[object]]
    resolve: Callable[[MutationPlan], MutationPlan]
    journal: Journal
    generation: int
    target_identity: str
    template_version: str = "construction-group-template-v1"
    operation_id: str | None = None
    idempotency_key: str | None = None
    consumer_id: str | None = None
    operation_kind: str | None = None


@dataclass(frozen=True)
class GroupRowRequest:
    plan: MutationPlan
    source: Path
    output: Path
    sheet: str
    fields: dict[int, object]
    hyperlink: str | None = None
    context: PublicationContext | None = None


def recover_group_row(*, context: PublicationContext, operation: object, source: Path) -> str:
    """Hash-only recovery: finalise post-hash, re-resolve pre-hash, never overwrite a third hash."""
    values = operation if isinstance(operation, Mapping) else getattr(operation, "values", operation)
    if not isinstance(values, Mapping):
        raise GroupRowInsertionError("recovery_operation_invalid", stage="recovery")
    current, phase = sha256(source), str(values.get("phase"))
    operation_id, pre_hash, post_hash = str(values.get("operation_id")), values.get("pre_hash"), values.get("post_hash")
    if post_hash and current == post_hash:
        if phase == "published": _finalize(context, operation_id)
        return "finalize_only"
    if pre_hash and current == pre_hash and phase in {"planned", "staged", "native", "validated", "backup_verified"}:
        return "re_resolve_required"
    _manual_repair(context, operation_id, phase, "workbook_third_hash_manual_repair")
    return "manual_repair"


def _fsync(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _copy_verified(source: Path, destination: Path) -> str:
    shutil.copy2(source, destination)
    _fsync(destination)
    result = sha256(destination)
    if result != sha256(source):
        raise GroupRowInsertionError("staged_hash_mismatch", stage="stage")
    return result


_INTENT_VERSION = "group-row-intent-v2"
_MANIFEST_VERSION = "group-row-manifest-v2"


def _canonical_json(value: object) -> str:
    """Encode only finite, genuine JSON values; never coerce unknown objects."""
    def validate(current: object) -> None:
        if current is None or isinstance(current, (str, bool)):
            return
        if isinstance(current, int) and not isinstance(current, bool):
            return
        if isinstance(current, float):
            if math.isfinite(current):
                return
            raise ValueError("nonfinite JSON number")
        if isinstance(current, list):
            for item in current:
                validate(item)
            return
        if isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str):
                    raise ValueError("noncanonical JSON object key")
                validate(item)
            return
        raise ValueError("non-JSON value")

    validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _authority(context: PublicationContext) -> tuple[str, str, str]:
    identifiers = (context.operation_id, context.idempotency_key, context.consumer_id)
    if any(not isinstance(value, str) or not value.strip() for value in identifiers):
        raise GroupRowInsertionError("publication_authority_required", stage="authorize")
    operation_id, idempotency_key, consumer_id = identifiers
    try:
        if str(UUID(operation_id)) != operation_id:
            raise ValueError("noncanonical UUID")
    except ValueError as error:
        raise GroupRowInsertionError("publication_identity_invalid", stage="authorize", cause=error) from error
    if context.operation_kind != "new_row":
        raise GroupRowInsertionError("publication_operation_kind_mismatch", stage="preflight")
    return operation_id, idempotency_key, consumer_id


def _evidence(
    *,
    context: PublicationContext,
    request: GroupRowRequest,
    plan: MutationPlan,
    mode: str,
) -> tuple[str, str]:
    stable_strings = (
        context.target_identity, context.template_version, request.sheet,
        plan.construction_id, plan.canonical_rns, plan.workbook_identity, plan.workbook_hash,
    )
    if (
        not isinstance(request.fields, dict)
        or not isinstance(request.hyperlink, (str, type(None)))
        or any(not isinstance(value, str) or not value.strip() for value in stable_strings)
        or type(plan.registry_generation) is not int
        or type(context.generation) is not int
        or type(plan.target_row) is not int
        or plan.target_row < 2
        or canonical_rns_identity(plan.canonical_rns) != plan.canonical_rns
    ):
        raise GroupRowInsertionError("publication_intent_value_invalid", stage="authorize")
    try:
        fields: list[list[object]] = []
        for column, value in sorted(request.fields.items()):
            if type(column) is not int or not 1 <= column <= 16_384:
                raise ValueError("noncanonical field key")
            _canonical_json(value)
            fields.append([column, value])
        intent_digest = _digest({
            "operation_kind": context.operation_kind,
            "consumer_id": context.consumer_id,
            "construction_id": plan.construction_id,
            "canonical_rns": plan.canonical_rns,
            "fields": fields,
            "hyperlink": request.hyperlink,
        })
        manifest_digest = _digest({
            "mutation_mode": mode,
            "target_identity": context.target_identity,
            "sheet_identity": request.sheet,
            "template_identity": context.template_version,
            "workbook_identity": plan.workbook_identity,
            "workbook_pre_hash": plan.workbook_hash,
            "registry_generation": plan.registry_generation,
            "target_row": plan.target_row,
            "format_source_row": plan.target_row - 1,
        })
    except (TypeError, ValueError) as error:
        raise GroupRowInsertionError("publication_intent_value_invalid", stage="authorize", cause=error) from error
    return intent_digest, manifest_digest


def _operation_values(operation: object) -> Mapping[str, object]:
    values = operation if isinstance(operation, Mapping) else getattr(operation, "values", None)
    if not isinstance(values, Mapping):
        raise GroupRowInsertionError("legacy_publication_authority_invalid", stage="recovery")
    return values


def _existing_operation(
    operation: object,
    *,
    expected: Mapping[str, object],
) -> None:
    values = _operation_values(operation)
    if values.get("intent_version") != _INTENT_VERSION or values.get("manifest_version") != _MANIFEST_VERSION:
        raise GroupRowInsertionError("legacy_publication_authority_invalid", stage="recovery")
    required = ("owner_id", "pair_nonce", "operation_id", "idempotency_key", "consumer_id")
    if any(not isinstance(values.get(key), str) or not values.get(key) for key in required):
        raise GroupRowInsertionError("legacy_publication_authority_invalid", stage="recovery")
    if any(values.get(key) != value for key, value in expected.items()):
        raise GroupRowInsertionError("publication_intent_conflict", stage="recovery")


def _classify_existing(
    context: PublicationContext,
    operation: object,
    *,
    expected: Mapping[str, object],
    source: Path,
) -> dict[str, object]:
    """Classify a verified authority without mutating a live first publisher."""
    _existing_operation(operation, expected=expected)
    values = _operation_values(operation)
    # Authority is durable before the first publisher has copied its control
    # file. A concurrent loser must wait, never turn that live operation into
    # manual repair merely because pre-hash evidence is not written yet.
    recovery = "in_progress" if values.get("phase") == "planned" and not values.get("pre_hash") and not values.get("post_hash") else recover_group_row(context=context, operation=operation, source=source)
    return {
        "published": False,
        "operation_id": expected["operation_id"],
        "recovery": recovery,
    }


def _reserve(
    context: PublicationContext,
    plan: MutationPlan,
    directory: Path,
    mode: str,
    *,
    operation_id: str,
    idempotency_key: str,
    consumer_id: str,
    sheet_identity: str,
    intent_digest: str,
    manifest_digest: str,
) -> tuple[object, bool]:
    return context.journal.reserve(
        nonce_factory=lambda: (str(uuid4()), str(uuid4())),
        operation_id=operation_id, idempotency_key=idempotency_key, consumer_id=consumer_id,
        construction_id=plan.construction_id, operation_kind="new_row", mutation_mode=mode,
        target_identity=context.target_identity, sheet_identity=sheet_identity, template_version=context.template_version,
        expected_generation=context.generation, intent_version=_INTENT_VERSION, intent_digest=intent_digest,
        manifest_version=_MANIFEST_VERSION, manifest_digest=manifest_digest,
        operation_directory=str(directory), canonical_rns=plan.canonical_rns,
    )


def _recheck(context: PublicationContext, plan: MutationPlan, source: Path) -> MutationPlan:
    current = context.resolve(plan)
    if (current.workbook_identity != plan.workbook_identity or current.workbook_hash != sha256(source)
            or current.registry_generation != context.generation or current.construction_id != plan.construction_id
            or current.canonical_rns != plan.canonical_rns or current.target_row != plan.target_row
            or current.mode != plan.mode):
        raise GroupRowInsertionError("group_row_revalidation_failed", stage="revalidate")
    return current


def _manual_repair(context: PublicationContext, operation_id: str, phase: str, code: str) -> None:
    try:
        context.journal.transition(operation_id, expected_phase=phase, next_phase="manual_repair", failure_code=code)
    except Exception:
        pass


def _finalize(context: PublicationContext, operation_id: str) -> None:
    for flag in ("capability_finalized", "binding_finalized", "history_finalized", "report_finalized"):
        context.journal.finalize_flag(operation_id, flag)
    context.journal.transition(operation_id, expected_phase="published", next_phase="finalized")


def publish_group_row(request: GroupRowRequest, *, native_script: Path, operation_directory: Path) -> dict[str, object]:
    """Publish through lock, resolver, journal, paired native Excel and oracle."""
    if request.context is None:
        raise GroupRowInsertionError("publication_authority_required", stage="authorize")
    context, plan = request.context, request.plan
    operation_id, idempotency_key, consumer_id = _authority(context)
    if plan.mode not in {"existing_blank", "insert_before_header"}:
        raise GroupRowInsertionError("group_row_plan_invalid", stage="preflight")
    mode = "blank_fill" if plan.mode == "existing_blank" else "middle_insert"
    intent_digest, manifest_digest = _evidence(context=context, request=request, plan=plan, mode=mode)
    directory = operation_directory / operation_id
    expected = {
        "operation_id": operation_id,
        "idempotency_key": idempotency_key,
        "consumer_id": consumer_id,
        "construction_id": plan.construction_id,
        "canonical_rns": plan.canonical_rns,
        "operation_kind": "new_row",
        "mutation_mode": mode,
        "target_identity": context.target_identity,
        "sheet_identity": request.sheet,
        "template_version": context.template_version,
        # This immutable value belongs to the original plan. A restarted
        # integration may observe a newer registry generation, but an exact
        # operation replay must still bind to its stored authority first.
        "expected_generation": plan.registry_generation,
        "intent_version": _INTENT_VERSION,
        "intent_digest": intent_digest,
        "manifest_version": _MANIFEST_VERSION,
        "manifest_digest": manifest_digest,
        "operation_directory": str(directory),
    }
    phase, created_operation = "planned", False
    try:
        with context.lock():
            existing = context.journal.get(operation_id)
            if existing is not None:
                return _classify_existing(context, existing, expected=expected, source=request.source)
            if plan.registry_generation != context.generation:
                raise GroupRowInsertionError("registry_generation_stale", stage="authorize")
            plan = _recheck(context, plan, request.source)
            try:
                stored, created_operation = _reserve(
                    context, plan, directory, mode,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    consumer_id=consumer_id,
                    sheet_identity=request.sheet,
                    intent_digest=intent_digest,
                    manifest_digest=manifest_digest,
                )
            except RegistryConflictError as error:
                stored = context.journal.get(operation_id)
                if stored is None:
                    raise GroupRowInsertionError("publication_intent_conflict", stage="recovery", cause=error) from error
                return _classify_existing(context, stored, expected=expected, source=request.source)
            if not created_operation:
                return _classify_existing(context, stored, expected=expected, source=request.source)
            stored_values = _operation_values(stored)
            owner, pair = stored_values.get("owner_id"), stored_values.get("pair_nonce")
            if not isinstance(owner, str) or not owner or not isinstance(pair, str) or not pair:
                raise GroupRowInsertionError("legacy_publication_authority_invalid", stage="recovery")
            directory.mkdir(mode=0o700, parents=True, exist_ok=False)
            control, candidate = directory / "control.xlsx", directory / "candidate.xlsx"
            staged_hash = _copy_verified(request.source, control); _copy_verified(request.source, candidate)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="staged", hashes={"pre_hash": plan.workbook_hash, "staged_hash": staged_hash})
            phase = "staged"
            if not native_excel_available():
                code = "excel_required_for_middle_insert" if mode == "middle_insert" else "excel_required_for_group_publication"
                raise GroupRowInsertionError(code, stage="pre_open")
            if mode == "middle_insert" and not insertion_is_structurally_safe(inspect_workbook(request.source, request.sheet), plan.target_row):
                raise GroupRowInsertionError("group_row_structure_unsafe", stage="preflight")
            native = NativeInsertRequest(operation_id, owner, pair, control, candidate, plan.target_row,
                directory / "excel-lease.json", directory / "lease-ack.json", request.sheet, request.fields, request.hyperlink, mode)
            # The trusted adapter owns K2B1 verification, the staged->native
            # CAS and durable audit ACK before granting helper stdin ``open``.
            # Do not replay that transition here.
            result = run_native_insert(native, native_script, context.journal)
            if result.get("durable_phase") != "native":
                raise GroupRowInsertionError("excel_native_phase_missing", stage="native")
            phase = "native"
            try:
                original, control_manifest = manifest_for(request.source, request.sheet), manifest_for(control, request.sheet)
                candidate_manifest = manifest_for(candidate, request.sheet, insertion_row=plan.target_row)
                validate_control(original, control_manifest)
                if mode == "middle_insert":
                    validate_insertion(control_manifest, candidate_manifest, plan.target_row)
                    validate_inserted_row(
                        control,
                        candidate,
                        sheet_name=request.sheet,
                        insertion_row=plan.target_row,
                        fields=request.fields,
                        hyperlink=request.hyperlink,
                    )
                    validate_dependent_registry_references(
                        control,
                        candidate,
                        insertion_row=plan.target_row,
                        registry_sheet=request.sheet,
                    )
                    validate_x14_cf_middle_insert(
                        control,
                        candidate,
                        sheet_name=request.sheet,
                        insertion_row=plan.target_row,
                        format_source_row=plan.target_row - 1,
                    )
                    validate_filter_database_middle_insert(
                        control,
                        candidate,
                        sheet_name=request.sheet,
                        insertion_row=plan.target_row,
                    )
                    validate_worksheet_structure_middle_insert(
                        control,
                        candidate,
                        sheet_name=request.sheet,
                        insertion_row=plan.target_row,
                    )
                else:
                    validate_blank_fill(
                        control_manifest,
                        candidate_manifest,
                        target_row=plan.target_row,
                        fields=request.fields,
                        hyperlink=request.hyperlink,
                    )
            except (
                MutationManifestError,
                OPCWorksheetX14CfInsertionOracleError,
                OPCWorkbookFilterDatabaseInsertionOracleError,
                OPCWorksheetStructureInsertionOracleError,
            ) as error:
                raise GroupRowInsertionError(error.code, stage="validate", cause=error) from error
            except Exception as error:
                raise GroupRowInsertionError("workbook_manifest_validation_failed", stage="validate", cause=error) from error
            if sha256(request.source) != plan.workbook_hash: raise GroupRowInsertionError("workbook_pre_hash_mismatch", stage="pre_replace")
            _fsync(candidate)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="validated", hashes={"control_hash": sha256(control), "validation_digest": candidate_manifest.digest}); phase = "validated"
            backup = directory / "backup.xlsx"; backup_hash = _copy_verified(request.source, backup)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="backup_verified", hashes={"backup_hash": backup_hash}); phase = "backup_verified"
            context.journal.record_post_hash(operation_id, expected_phase=phase, post_hash=sha256(candidate))
            _recheck(context, plan, request.source)
            os.replace(candidate, request.output)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="published")
            _finalize(context, operation_id)
            return {"mode": mode, "row": plan.target_row, "published": True, "operation_id": operation_id, "manifest": candidate_manifest.digest}
    except GroupRowInsertionError as error:
        if created_operation: _manual_repair(context, operation_id, phase, error.code)
        raise
    except NativeExcelError as error:
        code = "excel_required_for_group_publication" if mode == "blank_fill" and error.code == "excel_required_for_middle_insert" else error.code
        durable_phase = error.durable_phase if error.durable_phase in {"staged", "native"} else phase
        if created_operation: _manual_repair(context, operation_id, durable_phase, code)
        raise GroupRowInsertionError(code, stage=error.stage, cause=error, cleanup=error.cleanup) from error
    except Exception as error:
        if created_operation: _manual_repair(context, operation_id, phase, "group_row_failed")
        raise GroupRowInsertionError("group_row_failed", stage=phase, cause=error) from error
