"""Durable, fail-closed publisher for one resolved construction-group row."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Callable, Mapping, Protocol
from uuid import uuid4

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
from rns_import_server.workbook_mutation_manifest import manifest_for, validate_control, validate_insertion
from rns_import_server.workbook_structure import inspect_workbook, insertion_is_structurally_safe


class GroupRowInsertionError(RuntimeError):
    """Public recovery envelope retaining stage and original system failure."""
    def __init__(self, code: str, *, stage: str, cause: BaseException | None = None, cleanup: BaseException | None = None):
        self.code, self.stage, self.cause, self.cleanup = code, stage, cause, cleanup
        detail = f": {cause}" if cause else ""
        if cleanup:
            detail += f"; cleanup: {cleanup}"
        super().__init__(f"{code}@{stage}{detail}")


class Journal(Protocol):
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
    native_runner: Callable[[NativeInsertRequest, Path], dict[str, object]] | None = None


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


def _create(context: PublicationContext, plan: MutationPlan, directory: Path, mode: str) -> tuple[str, str, str]:
    operation_id, owner, pair = str(uuid4()), str(uuid4()), str(uuid4())
    context.journal.create(operation_id=operation_id, idempotency_key=operation_id, consumer_id=operation_id, owner_id=owner,
        pair_nonce=pair, construction_id=plan.construction_id, operation_kind="new_row", mutation_mode=mode,
        target_identity=context.target_identity, sheet_identity="workbook-group-resolution-v1", template_version=context.template_version,
        expected_generation=context.generation, intent_version="workbook-group-resolution-v1", intent_digest=plan.workbook_hash,
        manifest_version="native-group-row-insertion-v1", manifest_digest=plan.workbook_hash,
        operation_directory=str(directory), canonical_rns=plan.canonical_rns)
    return operation_id, owner, pair


def _recheck(context: PublicationContext, plan: MutationPlan, source: Path) -> MutationPlan:
    current = context.resolve(plan)
    if (current.workbook_identity != plan.workbook_identity or current.workbook_hash != sha256(source)
            or current.registry_generation != context.generation or current.construction_id != plan.construction_id
            or current.canonical_rns != plan.canonical_rns or current.target_row != plan.target_row):
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
        raise GroupRowInsertionError("publication_context_required", stage="authorize")
    context, plan = request.context, request.plan
    if plan.registry_generation != context.generation:
        raise GroupRowInsertionError("registry_generation_stale", stage="authorize")
    directory = operation_directory / str(uuid4()); directory.mkdir(parents=True, exist_ok=False)
    phase, operation_id = "planned", ""
    try:
        with context.lock():
            plan = _recheck(context, plan, request.source)
            mode = "blank_fill" if plan.mode == "existing_blank" else "middle_insert"
            if plan.mode not in {"existing_blank", "insert_before_header"}:
                raise GroupRowInsertionError("group_row_plan_invalid", stage="preflight")
            operation_id, owner, pair = _create(context, plan, directory, mode)
            control, candidate = directory / "control.xlsx", directory / "candidate.xlsx"
            staged_hash = _copy_verified(request.source, control); _copy_verified(request.source, candidate)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="staged", hashes={"pre_hash": plan.workbook_hash, "staged_hash": staged_hash})
            phase = "staged"
            if context.native_runner is None and not native_excel_available():
                code = "excel_required_for_middle_insert" if mode == "middle_insert" else "excel_required_for_group_publication"
                raise GroupRowInsertionError(code, stage="pre_open")
            if mode == "middle_insert" and not insertion_is_structurally_safe(inspect_workbook(request.source, request.sheet), plan.target_row):
                raise GroupRowInsertionError("group_row_structure_unsafe", stage="preflight")
            native = NativeInsertRequest(operation_id, owner, pair, control, candidate, plan.target_row,
                directory / "excel-lease.json", directory / "lease-ack.json", request.sheet, request.fields, request.hyperlink)
            result = context.native_runner(native, native_script) if context.native_runner else run_native_insert(native, script=native_script)
            lease = result.get("lease")
            if not isinstance(lease, dict):
                raise GroupRowInsertionError("excel_lease_missing", stage="lease")
            context.journal.transition(operation_id, expected_phase=phase, next_phase="native", excel_lease=lease); phase = "native"
            original, control_manifest = manifest_for(request.source, request.sheet), manifest_for(control, request.sheet)
            candidate_manifest = manifest_for(candidate, request.sheet, insertion_row=plan.target_row)
            validate_control(original, control_manifest)
            if mode == "middle_insert":
                validate_insertion(control_manifest, candidate_manifest, plan.target_row)
                try:
                    validate_x14_cf_middle_insert(
                        control,
                        candidate,
                        sheet_name=request.sheet,
                        insertion_row=plan.target_row,
                        format_source_row=plan.target_row - 1,
                    )
                except OPCWorksheetX14CfInsertionOracleError as error:
                    raise GroupRowInsertionError(error.code, stage="validate", cause=error) from error
                try:
                    validate_filter_database_middle_insert(
                        control,
                        candidate,
                        sheet_name=request.sheet,
                        insertion_row=plan.target_row,
                    )
                except OPCWorkbookFilterDatabaseInsertionOracleError as error:
                    raise GroupRowInsertionError(error.code, stage="validate", cause=error) from error
                try:
                    validate_worksheet_structure_middle_insert(
                        control,
                        candidate,
                        sheet_name=request.sheet,
                        insertion_row=plan.target_row,
                    )
                except OPCWorksheetStructureInsertionOracleError as error:
                    raise GroupRowInsertionError(error.code, stage="validate", cause=error) from error
            if sha256(request.source) != plan.workbook_hash: raise GroupRowInsertionError("workbook_pre_hash_mismatch", stage="pre_replace")
            _fsync(candidate)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="validated", hashes={"control_hash": sha256(control), "validation_digest": candidate_manifest.digest}, excel_lease=lease); phase = "validated"
            backup = directory / "backup.xlsx"; backup_hash = _copy_verified(request.source, backup)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="backup_verified", hashes={"backup_hash": backup_hash}); phase = "backup_verified"
            context.journal.record_post_hash(operation_id, expected_phase=phase, post_hash=sha256(candidate))
            _recheck(context, plan, request.source)
            os.replace(candidate, request.output)
            context.journal.transition(operation_id, expected_phase=phase, next_phase="published")
            _finalize(context, operation_id)
            return {"mode": mode, "row": plan.target_row, "published": True, "operation_id": operation_id, "manifest": candidate_manifest.digest}
    except GroupRowInsertionError as error:
        if operation_id: _manual_repair(context, operation_id, phase, error.code)
        raise
    except NativeExcelError as error:
        if operation_id: _manual_repair(context, operation_id, phase, error.code)
        raise GroupRowInsertionError(error.code, stage=error.stage, cause=error) from error
    except Exception as error:
        if operation_id: _manual_repair(context, operation_id, phase, "group_row_failed")
        raise GroupRowInsertionError("group_row_failed", stage=phase, cause=error) from error
