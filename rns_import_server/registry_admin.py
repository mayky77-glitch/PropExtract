"""Transport-neutral admin projection over the accepted registry storage API."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Literal

from rns_import_server.construction_registry import Construction, ConstructionValidationError
from rns_import_server.registry_storage import (
    RegistryConflictError,
    RegistryError,
    RegistryStaleError,
    RegistryStorage,
)


class RegistryAdminCode(StrEnum):
    OK = "ok"
    INVALID = "invalid"
    DUPLICATE = "duplicate"
    STALE_GENERATION = "stale_generation"
    ACTIVE_JOB = "active_job"
    ACTIVE_JOB_WAIT_REQUIRED = "active_job_wait_required"
    NOT_FOUND = "not_found"
    DRAFT_ONLY = "draft_only"
    FORBIDDEN_STATUS_TRANSITION = "forbidden_status_transition"
    BINDING_ALIGNMENT_REQUIRED = "binding_alignment_required"
    BINDING_REVALIDATION_REQUIRED = "binding_revalidation_required"
    BINDING_REVALIDATION_FAILED = "binding_revalidation_failed"


@dataclass(frozen=True)
class BindingProjection:
    construction_id: str
    workbook_contract_id: str
    target_identity: str
    sheet_identity: str
    template_version: str
    verified_state: str


@dataclass(frozen=True)
class RegistryListProjection:
    generation: int
    constructions: tuple[Construction, ...]
    bindings: tuple[BindingProjection, ...]
    conflicts: tuple[dict[str, object], ...]

    @property
    def routable_constructions(self) -> tuple[Construction, ...]:
        return tuple(item for item in self.constructions if item.status == "active")


@dataclass(frozen=True)
class RegistryAdminResult:
    code: RegistryAdminCode
    generation: int
    construction: Construction | None = None


ActiveJobPolicy = Literal["reject", "wait"]
BindingRevalidator = Callable[[BindingProjection], bool]


class RegistryAdminService:
    """Validated service boundary; it does not activate or provision XLSX blocks."""

    def __init__(self, storage: RegistryStorage):
        self._storage = storage

    def _bindings(self, construction_id: str | None = None) -> tuple[BindingProjection, ...]:
        query = (
            "SELECT construction_id, workbook_contract_id, target_identity, sheet_identity, "
            "template_version, verified_state FROM construction_bindings"
        )
        values: tuple[str, ...] = ()
        if construction_id is not None:
            query += " WHERE construction_id=?"
            values = (construction_id,)
        query += " ORDER BY id"
        return tuple(BindingProjection(**dict(row)) for row in self._storage.connection.execute(query, values))

    def list(self) -> RegistryListProjection:
        return RegistryListProjection(
            generation=self._storage.generation,
            constructions=tuple(self._storage.list_constructions()),
            bindings=self._bindings(),
            conflicts=tuple(self._storage.conflicts()),
        )

    def _job_gate(self, active_job: bool, policy: ActiveJobPolicy) -> RegistryAdminResult | None:
        if policy not in {"reject", "wait"}:
            return RegistryAdminResult(RegistryAdminCode.INVALID, self._storage.generation)
        if not active_job:
            return None
        code = RegistryAdminCode.ACTIVE_JOB if policy == "reject" else RegistryAdminCode.ACTIVE_JOB_WAIT_REQUIRED
        return RegistryAdminResult(code, self._storage.generation)

    def _result_from_error(self, error: Exception) -> RegistryAdminResult:
        if isinstance(error, RegistryStaleError):
            code = RegistryAdminCode.STALE_GENERATION
        elif isinstance(error, RegistryConflictError):
            code = RegistryAdminCode.DUPLICATE
        elif isinstance(error, ConstructionValidationError):
            code = RegistryAdminCode.INVALID
        else:
            code = RegistryAdminCode.NOT_FOUND
        return RegistryAdminResult(code, self._storage.generation)

    def create_provision_request(
        self, *, code_prefix: str, official_name: str, expected_generation: int,
        active_job: bool = False, active_job_policy: ActiveJobPolicy = "reject",
    ) -> RegistryAdminResult:
        if blocked := self._job_gate(active_job, active_job_policy):
            return blocked
        try:
            draft = self._storage.create_construction(
                code_prefix=code_prefix, official_name=official_name, status="draft",
                expected_generation=expected_generation,
            )
        except (ConstructionValidationError, RegistryConflictError, RegistryStaleError, RegistryError) as error:
            return self._result_from_error(error)
        return RegistryAdminResult(RegistryAdminCode.OK, self._storage.generation, draft)

    def correct_draft(
        self, construction_id: str, *, code_prefix: str, official_name: str,
        expected_generation: int, expected_row_revision: int,
        active_job: bool = False, active_job_policy: ActiveJobPolicy = "reject",
    ) -> RegistryAdminResult:
        if blocked := self._job_gate(active_job, active_job_policy):
            return blocked
        current = self._storage.get_construction(construction_id)
        if current is None:
            return RegistryAdminResult(RegistryAdminCode.NOT_FOUND, self._storage.generation)
        if current.status != "draft":
            if self._bindings(construction_id) and (current.code_prefix != code_prefix or current.official_name != official_name):
                return RegistryAdminResult(RegistryAdminCode.BINDING_ALIGNMENT_REQUIRED, self._storage.generation, current)
            return RegistryAdminResult(RegistryAdminCode.DRAFT_ONLY, self._storage.generation, current)
        if self._bindings(construction_id):
            return RegistryAdminResult(RegistryAdminCode.BINDING_ALIGNMENT_REQUIRED, self._storage.generation, current)
        try:
            updated = self._storage.update_construction(
                construction_id, code_prefix=code_prefix, official_name=official_name,
                expected_generation=expected_generation, expected_row_revision=expected_row_revision,
            )
        except (ConstructionValidationError, RegistryConflictError, RegistryStaleError, RegistryError) as error:
            return self._result_from_error(error)
        return RegistryAdminResult(RegistryAdminCode.OK, self._storage.generation, updated)

    def change_status(
        self, construction_id: str, *, status: str, expected_generation: int,
        active_job: bool = False, active_job_policy: ActiveJobPolicy = "reject",
        binding_revalidator: BindingRevalidator | None = None,
    ) -> RegistryAdminResult:
        if blocked := self._job_gate(active_job, active_job_policy):
            return blocked
        current = self._storage.get_construction(construction_id)
        if current is None:
            return RegistryAdminResult(RegistryAdminCode.NOT_FOUND, self._storage.generation)
        if current.status == "draft":
            return RegistryAdminResult(RegistryAdminCode.FORBIDDEN_STATUS_TRANSITION, self._storage.generation, current)
        if status not in {"active", "archived"}:
            return RegistryAdminResult(RegistryAdminCode.FORBIDDEN_STATUS_TRANSITION, self._storage.generation, current)
        if current.status == "archived" and status == "active":
            bindings = self._bindings(construction_id)
            if binding_revalidator is None:
                return RegistryAdminResult(RegistryAdminCode.BINDING_REVALIDATION_REQUIRED, self._storage.generation, current)
            if len(bindings) != 1 or not binding_revalidator(bindings[0]):
                return RegistryAdminResult(RegistryAdminCode.BINDING_REVALIDATION_FAILED, self._storage.generation, current)
        try:
            updated = self._storage.update_status(construction_id, status, expected_generation=expected_generation)
        except (ConstructionValidationError, RegistryStaleError, RegistryError) as error:
            return self._result_from_error(error)
        return RegistryAdminResult(RegistryAdminCode.OK, self._storage.generation, updated)
