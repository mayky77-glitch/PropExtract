"""Transport-neutral admin projection over the accepted registry storage API."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import threading
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
StorageFactory = Callable[[], RegistryStorage]


class RegistryAdminService:
    """Validated service boundary; it does not activate or provision XLSX blocks."""

    def __init__(self, storage: RegistryStorage | StorageFactory):
        """Create a service with one SQLite connection per request thread.

        Passing an existing ``RegistryStorage`` remains supported.  Its path
        and timeout become a factory for thread-owned connections; the passed
        connection is never shared with ``ThreadingHTTPServer`` handlers.
        Tests or hosts that need custom construction can pass a factory.
        """
        if callable(storage):
            self._storage_factory = storage
        else:
            path = storage.path
            read_only = storage.read_only
            timeout_ms = storage.timeout_ms

            def factory() -> RegistryStorage:
                return RegistryStorage(path, read_only=read_only, timeout_ms=timeout_ms)

            self._storage_factory = factory
        self._thread_local = threading.local()

    def _storage_for_thread(self) -> RegistryStorage:
        storage = getattr(self._thread_local, "storage", None)
        if storage is None:
            storage = self._storage_factory()
            self._thread_local.storage = storage
        return storage

    def close_thread_storage(self) -> None:
        """Close the calling thread's owned connection, if it was opened."""
        storage = getattr(self._thread_local, "storage", None)
        if storage is not None:
            storage.close()
            del self._thread_local.storage

    def _bindings(self, construction_id: str | None = None) -> tuple[BindingProjection, ...]:
        bindings = self._storage_for_thread().read_snapshot().bindings
        if construction_id is not None:
            bindings = tuple(item for item in bindings if item["construction_id"] == construction_id)
        return tuple(BindingProjection(**binding) for binding in bindings)

    def list(self) -> RegistryListProjection:
        snapshot = self._storage_for_thread().read_snapshot()
        return RegistryListProjection(
            generation=snapshot.generation,
            constructions=snapshot.constructions,
            bindings=tuple(BindingProjection(**binding) for binding in snapshot.bindings),
            conflicts=snapshot.conflicts,
        )

    def _job_gate(self, active_job: bool, policy: ActiveJobPolicy) -> RegistryAdminResult | None:
        storage = self._storage_for_thread()
        if policy not in {"reject", "wait"}:
            return RegistryAdminResult(RegistryAdminCode.INVALID, storage.generation)
        if not active_job:
            return None
        code = RegistryAdminCode.ACTIVE_JOB if policy == "reject" else RegistryAdminCode.ACTIVE_JOB_WAIT_REQUIRED
        return RegistryAdminResult(code, storage.generation)

    def _result_from_error(self, error: Exception) -> RegistryAdminResult:
        storage = self._storage_for_thread()
        if isinstance(error, RegistryStaleError):
            code = RegistryAdminCode.STALE_GENERATION
        elif isinstance(error, RegistryConflictError):
            code = RegistryAdminCode.DUPLICATE
        elif isinstance(error, ConstructionValidationError):
            code = RegistryAdminCode.INVALID
        else:
            code = RegistryAdminCode.NOT_FOUND
        return RegistryAdminResult(code, storage.generation)

    def create_provision_request(
        self, *, code_prefix: str, official_name: str, expected_generation: int,
        active_job: bool = False, active_job_policy: ActiveJobPolicy = "reject",
    ) -> RegistryAdminResult:
        if blocked := self._job_gate(active_job, active_job_policy):
            return blocked
        storage = self._storage_for_thread()
        try:
            draft = storage.create_construction(
                code_prefix=code_prefix, official_name=official_name, status="draft",
                expected_generation=expected_generation,
            )
        except (ConstructionValidationError, RegistryConflictError, RegistryStaleError, RegistryError) as error:
            return self._result_from_error(error)
        return RegistryAdminResult(RegistryAdminCode.OK, storage.generation, draft)

    def correct_draft(
        self, construction_id: str, *, code_prefix: str, official_name: str,
        expected_generation: int, expected_row_revision: int,
        active_job: bool = False, active_job_policy: ActiveJobPolicy = "reject",
    ) -> RegistryAdminResult:
        if blocked := self._job_gate(active_job, active_job_policy):
            return blocked
        storage = self._storage_for_thread()
        current = storage.get_construction(construction_id)
        if current is None:
            return RegistryAdminResult(RegistryAdminCode.NOT_FOUND, storage.generation)
        if current.status != "draft":
            if self._bindings(construction_id) and (current.code_prefix != code_prefix or current.official_name != official_name):
                return RegistryAdminResult(RegistryAdminCode.BINDING_ALIGNMENT_REQUIRED, storage.generation, current)
            return RegistryAdminResult(RegistryAdminCode.DRAFT_ONLY, storage.generation, current)
        if self._bindings(construction_id):
            return RegistryAdminResult(RegistryAdminCode.BINDING_ALIGNMENT_REQUIRED, storage.generation, current)
        try:
            updated = storage.update_construction(
                construction_id, code_prefix=code_prefix, official_name=official_name,
                expected_generation=expected_generation, expected_row_revision=expected_row_revision,
            )
        except (ConstructionValidationError, RegistryConflictError, RegistryStaleError, RegistryError) as error:
            return self._result_from_error(error)
        return RegistryAdminResult(RegistryAdminCode.OK, storage.generation, updated)

    def change_status(
        self, construction_id: str, *, status: str, expected_generation: int,
        active_job: bool = False, active_job_policy: ActiveJobPolicy = "reject",
        binding_revalidator: BindingRevalidator | None = None,
    ) -> RegistryAdminResult:
        if blocked := self._job_gate(active_job, active_job_policy):
            return blocked
        storage = self._storage_for_thread()
        current = storage.get_construction(construction_id)
        if current is None:
            return RegistryAdminResult(RegistryAdminCode.NOT_FOUND, storage.generation)
        if current.status == "draft":
            return RegistryAdminResult(RegistryAdminCode.FORBIDDEN_STATUS_TRANSITION, storage.generation, current)
        if status not in {"active", "archived"}:
            return RegistryAdminResult(RegistryAdminCode.FORBIDDEN_STATUS_TRANSITION, storage.generation, current)
        if current.status == "archived" and status == "active":
            bindings = self._bindings(construction_id)
            if binding_revalidator is None:
                return RegistryAdminResult(RegistryAdminCode.BINDING_REVALIDATION_REQUIRED, storage.generation, current)
            try:
                revalidated = len(bindings) == 1 and binding_revalidator(bindings[0])
            except Exception:
                return RegistryAdminResult(RegistryAdminCode.BINDING_REVALIDATION_FAILED, storage.generation, current)
            if not revalidated:
                return RegistryAdminResult(RegistryAdminCode.BINDING_REVALIDATION_FAILED, storage.generation, current)
        try:
            updated = storage.update_status(construction_id, status, expected_generation=expected_generation)
        except (ConstructionValidationError, RegistryStaleError, RegistryError) as error:
            return self._result_from_error(error)
        return RegistryAdminResult(RegistryAdminCode.OK, storage.generation, updated)
