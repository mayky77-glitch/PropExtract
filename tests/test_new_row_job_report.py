from __future__ import annotations

from rns_import_server.job_report import new_row_final_report_builder, new_row_final_report_snapshot
from rns_import_server.new_row_payload import ImportedNewRowState, ResolvedNewRowAuthority, build_new_row_payload


def test_memory_only_snapshot_is_detached_and_canonical() -> None:
    source = {"safe": ["value"]}
    state = ImportedNewRowState("action", "construction", "RU-00000000-00-2026", "Object", {1: "x"}, "Document", "https://example.test", source)
    authority = ResolvedNewRowAuthority("action", "construction", "RU-00000000-00-2026", "Object", "C", "D", "F")
    payload = build_new_row_payload(state, authority)
    first = new_row_final_report_snapshot(state, payload)
    source["safe"][0] = "changed"
    second = new_row_final_report_snapshot(state, payload)
    assert first == second and first["imported_summary"] == {"safe": ["value"]} and first is not second
    report = new_row_final_report_builder(state, payload)("action", 2, "a" * 64)
    assert report["final_state"]["workbook_sha256"] == "a" * 64 and "w_target" not in report
