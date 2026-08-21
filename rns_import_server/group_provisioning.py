"""Draft construction-group provisioning plans, without workbook mutation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol

from rns_import_server.registry_admin import RegistryAdminCode, RegistryAdminResult, RegistryAdminService


_BUSINESS_COLUMNS = tuple(range(1, 25)) + (27,)  # A:X and AA, never Y:Z.


class GroupProvisioningCode(StrEnum):
    PLANNED = "planned"
    JOB_AUTHORIZATION_REQUIRED = "job_authorization_required"
    PENDING_ALREADY_RESERVED = "pending_already_reserved"
    STALE_GENERATION = "stale_generation"
    NO_VALIDATED_ROW_PAIR = "no_validated_row_pair"
    DRAFT_REJECTED = "draft_rejected"


@dataclass(frozen=True)
class ProvisioningRow:
    """Read-only row evidence supplied by the workbook projection adapter."""

    number: int
    values: Mapping[int, object]
    is_business_row: bool
    is_preformatted: bool


@dataclass(frozen=True)
class GroupProvisioningProjection:
    workbook_identity: str
    workbook_hash: str
    registry_generation: int
    rows: tuple[ProvisioningRow, ...]


@dataclass(frozen=True)
class GroupProvisioningRequest:
    action_id: str
    job_authorization: str | None
    code_prefix: str
    official_name: str
    expected_generation: int


@dataclass(frozen=True)
class GroupProvisioningPlan:
    construction_id: str
    code_prefix: str
    official_name: str
    header_row: int
    bootstrap_row: int
    workbook_identity: str
    workbook_hash: str
    registry_generation: int


@dataclass(frozen=True)
class GroupProvisioningResult:
    code: GroupProvisioningCode
    draft: RegistryAdminResult | None = None
    plan: GroupProvisioningPlan | None = None
    publisher_result: object | None = None


class GroupProvisioningProjectionPort(Protocol):
    def read_projection(self) -> GroupProvisioningProjection: ...


class GroupProvisioningPendingPort(Protocol):
    """CAS owner for an authorized provisioning job."""

    def reserve_pending_to_planning(self, action_id: str, *, job_authorization: str) -> bool: ...


class GroupProvisioningPublisherPort(Protocol):
    """Optional later-gate handoff; this service never treats it as mutation."""

    def publish_plan(self, plan: GroupProvisioningPlan) -> object: ...


def _is_business_value(value: object) -> bool:
    # Formula tails are formatting/service evidence, not business occupancy.
    if value is None or value == "" or (isinstance(value, str) and not value.strip()):
        return False
    return not (isinstance(value, str) and value.startswith("="))


def _row_has_business_value(row: ProvisioningRow) -> bool:
    return row.is_business_row and any(_is_business_value(row.values.get(column)) for column in _BUSINESS_COLUMNS)


def _validated_blank(row: ProvisioningRow | None) -> bool:
    if row is None or not row.is_preformatted:
        return False
    return not any(_is_business_value(row.values.get(column)) for column in _BUSINESS_COLUMNS)


def plan_first_free_pair(projection: GroupProvisioningProjection) -> tuple[int, int] | None:
    """Return header/bootstrap rows from business data, never worksheet max-row."""
    rows = tuple(projection.rows)
    last_business = max((row.number for row in rows if _row_has_business_value(row)), default=0)
    header_row, bootstrap_row = last_business + 1, last_business + 2
    by_number = {row.number: row for row in rows}
    if not (_validated_blank(by_number.get(header_row)) and _validated_blank(by_number.get(bootstrap_row))):
        return None
    return header_row, bootstrap_row


class GroupProvisioningService:
    """Create a RegistryAdminService draft and return only a future plan."""

    def __init__(
        self,
        *,
        registry_admin: RegistryAdminService,
        projections: GroupProvisioningProjectionPort,
        pending: GroupProvisioningPendingPort,
        publisher: GroupProvisioningPublisherPort | None = None,
    ) -> None:
        self._registry_admin = registry_admin
        self._projections = projections
        self._pending = pending
        self._publisher = publisher

    def submit(self, request: GroupProvisioningRequest) -> GroupProvisioningResult:
        # A restarted pending action is a new job and must carry fresh authority.
        if not request.job_authorization:
            return GroupProvisioningResult(GroupProvisioningCode.JOB_AUTHORIZATION_REQUIRED)
        if not self._pending.reserve_pending_to_planning(
            request.action_id, job_authorization=request.job_authorization
        ):
            return GroupProvisioningResult(GroupProvisioningCode.PENDING_ALREADY_RESERVED)

        projection = self._projections.read_projection()
        if projection.registry_generation != request.expected_generation:
            return GroupProvisioningResult(GroupProvisioningCode.STALE_GENERATION)
        rows = plan_first_free_pair(projection)
        if rows is None:
            return GroupProvisioningResult(GroupProvisioningCode.NO_VALIDATED_ROW_PAIR)

        draft = self._registry_admin.create_provision_request(
            code_prefix=request.code_prefix,
            official_name=request.official_name,
            expected_generation=request.expected_generation,
        )
        if draft.code is RegistryAdminCode.STALE_GENERATION:
            return GroupProvisioningResult(GroupProvisioningCode.STALE_GENERATION, draft=draft)
        if draft.code is not RegistryAdminCode.OK or draft.construction is None:
            return GroupProvisioningResult(GroupProvisioningCode.DRAFT_REJECTED, draft=draft)

        # Creating the draft advances the registry generation. Read the
        # projection again so a later publisher receives current hash and
        # generation evidence, never the pre-draft snapshot.
        projection = self._projections.read_projection()
        if projection.registry_generation != draft.generation:
            return GroupProvisioningResult(GroupProvisioningCode.STALE_GENERATION, draft=draft)
        rows = plan_first_free_pair(projection)
        if rows is None:
            return GroupProvisioningResult(GroupProvisioningCode.NO_VALIDATED_ROW_PAIR, draft=draft)

        header_row, bootstrap_row = rows
        plan = GroupProvisioningPlan(
            construction_id=draft.construction.id,
            code_prefix=draft.construction.code_prefix,
            official_name=draft.construction.official_name,
            header_row=header_row,
            bootstrap_row=bootstrap_row,
            workbook_identity=projection.workbook_identity,
            workbook_hash=projection.workbook_hash,
            registry_generation=projection.registry_generation,
        )
        handoff = self._publisher.publish_plan(plan) if self._publisher is not None else None
        # Even a later-gate publisher response is evidence only: this gate has
        # neither an XLSX bridge nor authority to claim activation/publication.
        return GroupProvisioningResult(GroupProvisioningCode.PLANNED, draft, plan, handoff)

    def replan_draft(self, request: GroupProvisioningRequest, *, draft_id: str) -> GroupProvisioningResult:
        """Restart safely before any journal exists, with fresh job authority.

        A restart never revives an old pending action implicitly and never
        creates another construction. It reuses only the named current draft.
        """
        if not request.job_authorization:
            return GroupProvisioningResult(GroupProvisioningCode.JOB_AUTHORIZATION_REQUIRED)
        if not self._pending.reserve_pending_to_planning(
            request.action_id, job_authorization=request.job_authorization
        ):
            return GroupProvisioningResult(GroupProvisioningCode.PENDING_ALREADY_RESERVED)
        listed = self._registry_admin.list()
        draft_construction = next((item for item in listed.constructions if item.id == draft_id), None)
        if (
            draft_construction is None
            or draft_construction.status != "draft"
            or draft_construction.code_prefix != request.code_prefix
            or draft_construction.official_name != request.official_name
        ):
            return GroupProvisioningResult(GroupProvisioningCode.DRAFT_REJECTED)
        projection = self._projections.read_projection()
        if projection.registry_generation != listed.generation or projection.registry_generation != request.expected_generation:
            return GroupProvisioningResult(GroupProvisioningCode.STALE_GENERATION)
        rows = plan_first_free_pair(projection)
        if rows is None:
            return GroupProvisioningResult(GroupProvisioningCode.NO_VALIDATED_ROW_PAIR)
        header_row, bootstrap_row = rows
        draft = RegistryAdminResult(RegistryAdminCode.OK, listed.generation, draft_construction)
        plan = GroupProvisioningPlan(
            construction_id=draft_construction.id,
            code_prefix=draft_construction.code_prefix,
            official_name=draft_construction.official_name,
            header_row=header_row,
            bootstrap_row=bootstrap_row,
            workbook_identity=projection.workbook_identity,
            workbook_hash=projection.workbook_hash,
            registry_generation=projection.registry_generation,
        )
        handoff = self._publisher.publish_plan(plan) if self._publisher is not None else None
        return GroupProvisioningResult(GroupProvisioningCode.PLANNED, draft, plan, handoff)
