"""Pure immutable payload boundary for a requested new registry row."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping


ALLOWED_COLUMNS = frozenset((*range(1, 25), 27))


class NewRowPayloadError(ValueError):
    pass


def strict_json(value: object) -> object:
    """Deep-copy only genuine JSON values, rejecting formula-like text."""
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise NewRowPayloadError("new_row_payload_nonfinite")
        return value
    if type(value) is str:
        if value.lstrip()[:1] in {"=", "+", "-", "@"}:
            raise NewRowPayloadError("new_row_payload_formula_text")
        return value
    if type(value) is list:
        return [strict_json(item) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise NewRowPayloadError("new_row_payload_json_key")
        return {key: strict_json(item) for key, item in value.items()}
    raise NewRowPayloadError("new_row_payload_non_json")


def validate_fields(fields: object) -> dict[int, object]:
    if not isinstance(fields, Mapping):
        raise NewRowPayloadError("new_row_payload_fields_invalid")
    result: dict[int, object] = {}
    for column, value in fields.items():
        if type(column) is not int or column not in ALLOWED_COLUMNS or column in result:
            raise NewRowPayloadError("new_row_payload_column_invalid")
        result[column] = strict_json(value)
    return result


def canonical_json(value: object) -> str:
    return json.dumps(strict_json(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class ImportedNewRowState:
    action_id: str
    construction_id: str
    canonical_rns: str
    object_tail: str
    imported_fields: Mapping[int, object]
    resolution_c: object
    resolution_d: object
    resolution_f: object
    w_display: str
    w_target: str
    report_state: object = None

    def __post_init__(self) -> None:
        if any(type(value) is not str or not value for value in (self.action_id, self.construction_id, self.canonical_rns, self.object_tail, self.w_display, self.w_target)):
            raise NewRowPayloadError("new_row_payload_identity_invalid")
        fields = validate_fields(self.imported_fields)
        for column, value in ((3, self.resolution_c), (4, self.resolution_d), (6, self.resolution_f), (23, self.w_display)):
            fields[column] = strict_json(value)
        object.__setattr__(self, "imported_fields", MappingProxyType(deepcopy(fields)))
        object.__setattr__(self, "report_state", strict_json(deepcopy(self.report_state)))


@dataclass(frozen=True)
class NewRowPayload:
    action_id: str
    construction_id: str
    canonical_rns: str
    object_tail: str
    fields: Mapping[int, object]
    w_display: str
    w_target: str
    digest: str


def build_new_row_payload(state: ImportedNewRowState) -> NewRowPayload:
    if type(state) is not ImportedNewRowState:
        raise NewRowPayloadError("new_row_payload_state_invalid")
    fields = validate_fields(state.imported_fields)
    payload = {
        "action_id": state.action_id, "construction_id": state.construction_id, "canonical_rns": state.canonical_rns,
        "object_tail": state.object_tail, "fields": [[key, fields[key]] for key in sorted(fields)],
        "w_display": state.w_display, "w_target": state.w_target,
    }
    encoded = canonical_json(payload)
    return NewRowPayload(state.action_id, state.construction_id, state.canonical_rns, state.object_tail,
                         MappingProxyType(deepcopy(fields)), state.w_display, state.w_target,
                         hashlib.sha256(encoded.encode("utf-8")).hexdigest())
