"""Fail-closed, read-only workbook projections for the Wave3 planning ports.

This module deliberately has no durable-path producer.  A later gate must
inject :class:`WorkbookProjectionAuthority` only after it has proved the
target, workbook contract, sheet and template evidence together.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
import hashlib
import os
from pathlib import Path
from types import MappingProxyType
from typing import Protocol
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from rns_import_server.group_provisioning import GroupProvisioningProjection, ProvisioningRow
from rns_import_server.workbook_groups import SheetProjection, SheetRow


_BUSINESS_COLUMNS = tuple(range(1, 25)) + (27,)
_SUPPORTED_CELL_TYPES = (type(None), bool, int, float, str, date, datetime, time)


class WorkbookProjectionCode(StrEnum):
    OK = "ok"
    INVALID_AUTHORITY = "invalid_authority"
    UNSAFE_TARGET = "unsafe_target"
    SOURCE_UNSTABLE = "source_unstable"
    SOURCE_UNREADABLE = "source_unreadable"
    SHEET_MISMATCH = "sheet_mismatch"
    TEMPLATE_MISMATCH = "template_mismatch"
    UNSUPPORTED_CELL = "unsupported_cell"


@dataclass(frozen=True)
class TemplateCellEvidence:
    """Exact template cell evidence supplied by the future authority producer."""

    row: int
    column: int
    value: object


@dataclass(frozen=True, repr=False)
class WorkbookProjectionAuthority:
    """Immutable verified input; ``_target_path`` is private implementation data.

    IDs are evidence received from an authority producer, never inferred from
    the path or workbook bytes here.
    """

    target_identity: str
    workbook_contract_id: str
    sheet_identity: str
    template_version: str
    registry_generation: int
    template_cells: tuple[TemplateCellEvidence, ...]
    _target_path: str

    @classmethod
    def verified(
        cls,
        *,
        target_path: str,
        target_identity: str,
        workbook_contract_id: str,
        sheet_identity: str,
        template_version: str,
        registry_generation: int,
        template_cells: tuple[TemplateCellEvidence, ...],
    ) -> "WorkbookProjectionAuthority":
        return cls(
            target_identity=target_identity,
            workbook_contract_id=workbook_contract_id,
            sheet_identity=sheet_identity,
            template_version=template_version,
            registry_generation=registry_generation,
            template_cells=template_cells,
            _target_path=target_path,
        )


class WorkbookProjectionAuthorityPort(Protocol):
    def read_authority(self) -> WorkbookProjectionAuthority: ...


@dataclass(frozen=True)
class SourceObservation:
    device: int
    inode: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class WorkbookProjectionSnapshot:
    """The single stable read which backs both consumer-specific projections."""

    authority_identity: str
    workbook_contract_id: str
    pre_hash: str
    registry_generation: int
    source_observation: SourceObservation
    sheet: SheetProjection
    provisioning: GroupProvisioningProjection


@dataclass(frozen=True)
class WorkbookProjectionResult:
    code: WorkbookProjectionCode
    snapshot: WorkbookProjectionSnapshot | None = None


def _valid_scalar(value: object) -> bool:
    return type(value) in _SUPPORTED_CELL_TYPES


def _authority_is_well_formed(authority: object) -> bool:
    if type(authority) is not WorkbookProjectionAuthority:
        return False
    strings = (
        authority.target_identity,
        authority.workbook_contract_id,
        authority.sheet_identity,
        authority.template_version,
        authority._target_path,
    )
    if any(type(value) is not str or not value for value in strings):
        return False
    if type(authority.registry_generation) is not int or authority.registry_generation < 0:
        return False
    if type(authority.template_cells) is not tuple or not authority.template_cells:
        return False
    seen: set[tuple[int, int]] = set()
    for evidence in authority.template_cells:
        if type(evidence) is not TemplateCellEvidence:
            return False
        if type(evidence.row) is not int or type(evidence.column) is not int:
            return False
        if evidence.row < 1 or evidence.column < 1 or not _valid_scalar(evidence.value):
            return False
        key = (evidence.row, evidence.column)
        if key in seen:
            return False
        seen.add(key)
    return True


def _canonical_regular_path(path: str) -> Path | None:
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        return None
    candidate = Path(path)
    try:
        for component in (candidate, *candidate.parents):
            if component.is_symlink():
                return None
        if not candidate.is_file() or candidate.is_symlink():
            return None
    except OSError:
        return None
    return candidate


def _observe(path: Path) -> SourceObservation | None:
    try:
        stat = path.stat(follow_symlinks=False)
    except OSError:
        return None
    if not os.path.isfile(path):
        return None
    return SourceObservation(stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_scalar(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _cell_value(cell: object) -> object:
    value = cell.value  # type: ignore[attr-defined]
    if not _valid_scalar(value):
        raise TypeError("unsupported cell value")
    return value


def _project_rows(worksheet: object) -> tuple[tuple[SheetRow, ...], tuple[ProvisioningRow, ...]]:
    sheet_rows: list[SheetRow] = []
    provisioning_rows: list[ProvisioningRow] = []
    max_row = worksheet.max_row  # type: ignore[attr-defined]
    for number in range(1, max_row + 1):
        cells = {column: worksheet.cell(number, column) for column in _BUSINESS_COLUMNS}  # type: ignore[attr-defined]
        values = {column: _cell_value(cell) for column, cell in cells.items()}
        a_to_f = tuple(values[column] for column in range(1, 7))
        has_business = any(value not in (None, "") for value in values.values())
        preformatted = all(bool(getattr(cell, "has_style", False)) for cell in cells.values())
        is_business_row = has_business or preformatted
        sheet_rows.append(SheetRow(number, *a_to_f, is_business_row=is_business_row, is_preformatted=preformatted))
        provisioning_rows.append(
            ProvisioningRow(number, MappingProxyType(values), is_business_row=is_business_row, is_preformatted=preformatted)
        )
    return tuple(sheet_rows), tuple(provisioning_rows)


def project_workbook(authority: WorkbookProjectionAuthority) -> WorkbookProjectionResult:
    """Read one verified workbook snapshot and produce both planning projections."""
    if not _authority_is_well_formed(authority):
        return WorkbookProjectionResult(WorkbookProjectionCode.INVALID_AUTHORITY)
    path = _canonical_regular_path(authority._target_path)
    if path is None:
        return WorkbookProjectionResult(WorkbookProjectionCode.UNSAFE_TARGET)
    before = _observe(path)
    if before is None:
        return WorkbookProjectionResult(WorkbookProjectionCode.SOURCE_UNREADABLE)
    try:
        pre_hash = _sha256(path)
    except OSError:
        return WorkbookProjectionResult(WorkbookProjectionCode.SOURCE_UNREADABLE)
    if _observe(path) != before:
        return WorkbookProjectionResult(WorkbookProjectionCode.SOURCE_UNSTABLE)

    book = None
    try:
        book = load_workbook(path, read_only=True, data_only=False)
        if authority.sheet_identity not in book.sheetnames:
            return WorkbookProjectionResult(WorkbookProjectionCode.SHEET_MISMATCH)
        worksheet = book[authority.sheet_identity]
        for evidence in authority.template_cells:
            if not _same_scalar(_cell_value(worksheet.cell(evidence.row, evidence.column)), evidence.value):
                return WorkbookProjectionResult(WorkbookProjectionCode.TEMPLATE_MISMATCH)
        sheet_rows, provisioning_rows = _project_rows(worksheet)
    except TypeError:
        return WorkbookProjectionResult(WorkbookProjectionCode.UNSUPPORTED_CELL)
    except (OSError, ValueError, KeyError, RuntimeError, AttributeError, BadZipFile, InvalidFileException, ParseError):
        return WorkbookProjectionResult(WorkbookProjectionCode.SOURCE_UNREADABLE)
    finally:
        if book is not None:
            book.close()
    if _observe(path) != before:
        return WorkbookProjectionResult(WorkbookProjectionCode.SOURCE_UNSTABLE)

    sheet = SheetProjection.from_rows(
        authority.target_identity, pre_hash, authority.registry_generation, sheet_rows
    )
    provisioning = GroupProvisioningProjection(
        authority.target_identity, pre_hash, authority.registry_generation, provisioning_rows
    )
    return WorkbookProjectionResult(
        WorkbookProjectionCode.OK,
        WorkbookProjectionSnapshot(
            authority.target_identity,
            authority.workbook_contract_id,
            pre_hash,
            authority.registry_generation,
            before,
            sheet,
            provisioning,
        ),
    )


class WorkbookProjectionAdapter:
    """Read-only port adapter; a later gate owns authority production."""

    def __init__(self, authority: WorkbookProjectionAuthorityPort) -> None:
        self._authority = authority

    def read(self) -> WorkbookProjectionResult:
        try:
            authority = self._authority.read_authority()
        except Exception:
            return WorkbookProjectionResult(WorkbookProjectionCode.INVALID_AUTHORITY)
        return project_workbook(authority)
