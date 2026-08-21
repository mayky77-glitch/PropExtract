"""Port-only planning and reservation for a requested workbook row.

This boundary intentionally does not know how a workbook is opened, locked or
published. Hosts provide all three authorities as ports. In particular, the
CAS reservation happens before the second (authoritative) group resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Protocol

from rns_import_server.workbook_groups import (
    SheetProjection,
    WorkbookGroupCode,
    WorkbookGroupResolution,
    resolve_workbook_group,
)


_SUFFIX = re.compile(r"^[0-9]{4}$", flags=re.ASCII)


class NewRowCode(StrEnum):
    PLANNED = "planned"
    JOB_AUTHORIZATION_REQUIRED = "job_authorization_required"
    INVALID_SUFFIX = "invalid_suffix"
    PENDING_ALREADY_RESERVED = "pending_already_reserved"
    OBJECT_CODE_NAME_CONFLICT = "object_code_name_conflict"
    RESOLUTION_REJECTED = "resolution_rejected"
    PUBLICATION_REJECTED = "publication_rejected"


@dataclass(frozen=True)
class NewRowRequest:
    """Untrusted request data; ``object_code`` is formed by the service."""

    action_id: str
    job_authorization: str | None
    construction_id: str
    official_name: str
    code_prefix: str
    suffix: object
    object_name: str
    rns: object
    official_names: tuple[str, ...]


@dataclass(frozen=True)
class NewRowPublication:
    """Read-only evidence passed to a later publisher."""

    action_id: str
    object_code: str
    object_name: str
    resolution: WorkbookGroupResolution


@dataclass(frozen=True)
class NewRowPublicationResult:
    """Typed publisher response.

    A reservation can be reopened only when ``pre_hash_failure`` is explicitly
    proven by the publisher. An absent/false flag is deliberately fail-closed.
    """

    accepted: bool
    pre_hash_failure: bool = False
    detail: str | None = None


@dataclass(frozen=True)
class NewRowResult:
    code: NewRowCode
    object_code: str | None = None
    resolution: WorkbookGroupResolution | None = None
    publication: NewRowPublicationResult | None = None


class NewRowProjectionPort(Protocol):
    def read_projection(self) -> SheetProjection: ...


class NewRowPendingPort(Protocol):
    """Durable compare-and-set owner for ``pending -> publishing``."""

    def reserve_pending_to_publishing(self, action_id: str, *, job_authorization: str) -> bool: ...

    def reopen_after_pre_hash_failure(self, action_id: str, *, job_authorization: str) -> bool: ...


class NewRowPublisherPort(Protocol):
    def publish(self, publication: NewRowPublication) -> NewRowPublicationResult: ...


class NewRowService:
    """Validate then reserve one action; never mutate a workbook directly."""

    def __init__(
        self,
        *,
        projections: NewRowProjectionPort,
        pending: NewRowPendingPort,
        publisher: NewRowPublisherPort,
    ) -> None:
        self._projections = projections
        self._pending = pending
        self._publisher = publisher

    @staticmethod
    def full_object_code(code_prefix: str, suffix: object) -> str | None:
        """Build C exactly once on the server, retaining leading zeroes."""
        if not isinstance(code_prefix, str) or not isinstance(suffix, str) or not _SUFFIX.fullmatch(suffix):
            return None
        return f"{code_prefix}.{suffix}"

    def submit(self, request: NewRowRequest) -> NewRowResult:
        if not request.job_authorization:
            return NewRowResult(NewRowCode.JOB_AUTHORIZATION_REQUIRED)
        object_code = self.full_object_code(request.code_prefix, request.suffix)
        if object_code is None:
            return NewRowResult(NewRowCode.INVALID_SUFFIX)

        # This is the sole publication admission. The losing concurrent caller
        # must not resolve or call the publisher.
        if not self._pending.reserve_pending_to_publishing(
            request.action_id, job_authorization=request.job_authorization
        ):
            return NewRowResult(NewRowCode.PENDING_ALREADY_RESERVED, object_code=object_code)

        projection = self._projections.read_projection()
        resolution = resolve_workbook_group(
            projection,
            construction_id=request.construction_id,
            official_name=request.official_name,
            code_prefix=request.code_prefix,
            rns=request.rns,
            object_code=object_code,
            object_name=request.object_name,
            official_names=request.official_names,
        )
        if resolution.code is WorkbookGroupCode.OBJECT_CODE_NAME_CONFLICT:
            return NewRowResult(NewRowCode.OBJECT_CODE_NAME_CONFLICT, object_code, resolution)
        if not resolution.is_resolved:
            return NewRowResult(NewRowCode.RESOLUTION_REJECTED, object_code, resolution)

        publication = self._publisher.publish(
            NewRowPublication(request.action_id, object_code, request.object_name, resolution)
        )
        if not publication.accepted and publication.pre_hash_failure:
            # Do not infer this from an exception, a message, or a missing
            # hash. Only the typed proof authorizes reopening the action.
            self._pending.reopen_after_pre_hash_failure(
                request.action_id, job_authorization=request.job_authorization
            )
        code = NewRowCode.PLANNED if publication.accepted else NewRowCode.PUBLICATION_REJECTED
        return NewRowResult(code, object_code, resolution, publication)
