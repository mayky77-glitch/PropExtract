from pathlib import Path

import pytest

from rns_import_server.audit import sha256
from rns_import_server.workbook_cutover import WorkbookCutoverError, recovery_state, replace_verified


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


def sha256_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()
