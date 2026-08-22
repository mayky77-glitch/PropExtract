from __future__ import annotations

import pytest

from rns_import_server.new_row_payload import ImportedNewRowState, NewRowPayloadError, build_new_row_payload


def _state(**changes: object) -> ImportedNewRowState:
    values: dict[str, object] = dict(action_id="action", construction_id="construction", canonical_rns="RU-00000000-00-2026",
        object_tail="Object", imported_fields={1: "source", 27: "AA"}, resolution_c="C", resolution_d="D",
        resolution_f="F", w_display="Document", w_target="https://example.test/document", report_state={"status": "ready"})
    values.update(changes)
    return ImportedNewRowState(**values)  # type: ignore[arg-type]


def test_payload_binds_identity_overlay_and_detaches_imported_state() -> None:
    fields = {1: "source", 27: "AA"}
    state = _state(imported_fields=fields)
    payload = build_new_row_payload(state)
    fields[1] = "changed"
    assert (payload.action_id, payload.construction_id, payload.canonical_rns, payload.object_tail) == ("action", "construction", "RU-00000000-00-2026", "Object")
    assert (payload.fields[1], payload.fields[3], payload.fields[4], payload.fields[6], payload.fields[23], payload.w_display, payload.w_target) == ("source", "C", "D", "F", "Document", "Document", "https://example.test/document")


@pytest.mark.parametrize("fields", [{25: "x"}, {26: "x"}, {28: "x"}, {True: "x"}, {1: " =SUM(A1)"}, {1: float("nan")}, {1: object()}])
def test_payload_rejects_hostile_fields_before_any_side_effect(fields: dict[object, object]) -> None:
    with pytest.raises(NewRowPayloadError):
        _state(imported_fields=fields)
