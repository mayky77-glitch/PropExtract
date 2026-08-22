from __future__ import annotations

from rns_import_server.job_report import new_row_final_report_snapshot
from rns_import_server.new_row_payload import ImportedNewRowState, build_new_row_payload


def test_memory_only_snapshot_is_detached_and_canonical() -> None:
    source = {"safe": ["value"]}
    state = ImportedNewRowState("action", "construction", "RU-00000000-00-2026", "Object", {1: "x"}, "C", "D", "F", "Document", "https://example.test", source)
    payload = build_new_row_payload(state)
    first = new_row_final_report_snapshot(state, payload)
    source["safe"][0] = "changed"
    second = new_row_final_report_snapshot(state, payload)
    assert first == second and first["imported_summary"] == {"safe": ["value"]} and first is not second
