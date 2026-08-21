from pathlib import Path

import pytest

from rns_import_server.audit import sha256
import rns_import_server.workbook_cutover as cutover
from rns_import_server.workbook_cutover import WorkbookCutoverError, recovery_state, replace_verified, verify_pre_cutover_target


def test_replace_is_hash_verified_and_durable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate, target = tmp_path / "candidate.xlsx", tmp_path / "published.xlsx"
    candidate.write_bytes(b"candidate")
    flushed = []
    monkeypatch.setattr("rns_import_server.workbook_cutover.fsync_file", lambda path: flushed.append(("file", path)))
    monkeypatch.setattr("rns_import_server.workbook_cutover.fsync_directory", lambda path: flushed.append(("directory", path)))
    assert replace_verified(candidate=candidate, target=target, post_hash=sha256(candidate)) == sha256(target)
    assert not candidate.exists() and flushed == [("file", target), ("directory", tmp_path)]


@pytest.mark.parametrize(("phase", "contents", "expected"), [
    ("backup_verified", b"post", "publish_recovery"),
    ("published", b"post", "finalization_pending"),
    ("finalized", b"post", "already_finalized"),
    ("validated", b"pre", "re_resolve_required"),
    ("published", b"pre", "manual_repair"),
    ("backup_verified", b"third", "manual_repair"),
])
def test_recovery_is_hash_and_phase_exact(tmp_path: Path, phase: str, contents: bytes, expected: str) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "output.xlsx"
    source.write_bytes(b"pre"); output.write_bytes(contents)
    assert recovery_state(source=source, output=output, phase=phase, pre_hash=sha256(source), post_hash=sha256_bytes(b"post")) == expected


def test_replace_rejects_wrong_candidate_hash_without_mutating_target(tmp_path: Path) -> None:
    candidate, target = tmp_path / "candidate.xlsx", tmp_path / "published.xlsx"
    candidate.write_bytes(b"candidate"); target.write_bytes(b"old")
    with pytest.raises(WorkbookCutoverError, match="candidate_post_hash_mismatch"):
        replace_verified(candidate=candidate, target=target, post_hash=sha256(target))
    assert target.read_bytes() == b"old"


@pytest.mark.parametrize(("failure", "code", "stage"), [
    ("replace", "cutover_replace_failed", "replace"),
    ("target_fsync", "cutover_target_fsync_failed", "target_fsync"),
    ("parent_fsync", "cutover_parent_fsync_failed", "parent_fsync"),
])
def test_cutover_boundary_failures_are_typed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str, code: str, stage: str) -> None:
    candidate, target = tmp_path / "candidate.xlsx", tmp_path / "published.xlsx"
    candidate.write_bytes(b"candidate")
    if failure == "replace":
        monkeypatch.setattr(cutover.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace")))
    elif failure == "target_fsync":
        monkeypatch.setattr(cutover, "fsync_file", lambda *_: (_ for _ in ()).throw(OSError("file")))
    else:
        monkeypatch.setattr(cutover, "fsync_directory", lambda *_: (_ for _ in ()).throw(OSError("directory")))
    with pytest.raises(WorkbookCutoverError) as captured:
        replace_verified(candidate=candidate, target=target, post_hash=sha256(candidate))
    assert (captured.value.code, captured.value.stage, type(captured.value.cause)) == (code, stage, OSError)


def test_first_publication_refuses_existing_separate_target(tmp_path: Path) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "output.xlsx"
    source.write_bytes(b"pre"); output.write_bytes(b"third")
    with pytest.raises(WorkbookCutoverError, match="cutover_target_third_hash"):
        verify_pre_cutover_target(source=source, output=output, pre_hash=sha256(source))
    assert output.read_bytes() == b"third"


def test_missing_separate_output_uses_prepublication_source(tmp_path: Path) -> None:
    source, output = tmp_path / "source.xlsx", tmp_path / "output.xlsx"
    source.write_bytes(b"pre")
    verify_pre_cutover_target(source=source, output=output, pre_hash=sha256(source))
    assert recovery_state(source=source, output=output, phase="validated", pre_hash=sha256(source), post_hash="post") == "re_resolve_required"


def sha256_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()
