"""Durable, hash-exact XLSX cutover primitives.

This module deliberately owns no journal schema or finalization side effects.
Callers record durable ``post_hash`` before :func:`replace_verified` and use
the returned recovery classification under their publication lock.
"""
from __future__ import annotations

import os
from pathlib import Path

from rns_import_server.audit import sha256


class WorkbookCutoverError(RuntimeError):
    """A cutover boundary failed before its exact hash could be confirmed."""

    def __init__(self, code: str, *, stage: str, cause: BaseException | None = None):
        self.code, self.stage, self.cause = code, stage, cause
        super().__init__(code)


def fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _same_filesystem(candidate: Path, target: Path) -> bool:
    return candidate.stat().st_dev == target.parent.stat().st_dev


def replace_verified(*, candidate: Path, target: Path, post_hash: str) -> str:
    """Atomically replace ``target``, durably flush it, then prove its hash."""
    if not isinstance(post_hash, str) or not post_hash:
        raise WorkbookCutoverError("post_hash_required", stage="preflight")
    if not candidate.is_file() or not target.parent.is_dir():
        raise WorkbookCutoverError("cutover_path_missing", stage="preflight")
    if not _same_filesystem(candidate, target):
        raise WorkbookCutoverError("cutover_cross_filesystem", stage="preflight")
    if sha256(candidate) != post_hash:
        raise WorkbookCutoverError("candidate_post_hash_mismatch", stage="preflight")
    try:
        os.replace(candidate, target)
    except OSError as error:
        raise WorkbookCutoverError("cutover_replace_failed", stage="replace", cause=error) from error
    try:
        fsync_file(target)
    except OSError as error:
        raise WorkbookCutoverError("cutover_target_fsync_failed", stage="target_fsync", cause=error) from error
    try:
        fsync_directory(target.parent)
    except OSError as error:
        raise WorkbookCutoverError("cutover_parent_fsync_failed", stage="parent_fsync", cause=error) from error
    try:
        actual = sha256(target)
    except OSError as error:
        raise WorkbookCutoverError("cutover_target_hash_failed", stage="target_hash", cause=error) from error
    if actual != post_hash:
        raise WorkbookCutoverError("target_post_hash_mismatch", stage="target_hash")
    return actual


def authoritative_target(*, source: Path, output: Path) -> Path:
    """Existing output wins; otherwise source is the prepublication target."""
    return output if output.exists() else source


def verify_pre_cutover_target(*, source: Path, output: Path, pre_hash: str) -> None:
    """Require first publication's authoritative target to still be pre-hash.

    A separate existing output is already the authoritative target.  It cannot
    be overwritten by a fresh operation, even if it happens to match source.
    """
    target = authoritative_target(source=source, output=output)
    if not target.is_file():
        raise WorkbookCutoverError("cutover_target_missing", stage="target_recheck")
    try:
        current = sha256(target)
    except OSError as error:
        raise WorkbookCutoverError("cutover_target_hash_failed", stage="target_recheck", cause=error) from error
    if target != source:
        code = "cutover_target_pre_hash_requires_recovery" if current == pre_hash else "cutover_target_third_hash"
        raise WorkbookCutoverError(code, stage="target_recheck")
    if current != pre_hash:
        raise WorkbookCutoverError("cutover_source_pre_hash_mismatch", stage="target_recheck")


def recovery_state(*, source: Path, output: Path, phase: str, pre_hash: object, post_hash: object) -> str:
    """Classify hash/phase evidence without mutation.

    ``manual_repair`` includes missing and third-hash targets.  A pre-hash is
    only retryable before publication; after that it is contradictory evidence.
    """
    target = authoritative_target(source=source, output=output)
    if not target.is_file():
        return "manual_repair"
    current = sha256(target)
    if isinstance(post_hash, str) and post_hash and current == post_hash:
        if phase == "backup_verified":
            return "publish_recovery"
        if phase == "published":
            return "finalization_pending"
        if phase == "finalized":
            return "already_finalized"
        return "manual_repair"
    if isinstance(pre_hash, str) and pre_hash and current == pre_hash:
        if phase in {"planned", "staged", "native", "validated", "backup_verified"}:
            return "re_resolve_required"
    return "manual_repair"
