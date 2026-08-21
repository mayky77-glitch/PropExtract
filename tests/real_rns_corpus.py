"""Strict access boundary for the private, read-only real RNS workbook corpus."""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


RNS_REAL_CORPUS_PATH = "RNS_REAL_CORPUS_PATH"
REAL_RNS_CORPUS_SHA256 = "2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1"


def real_rns_corpus_path() -> Path:
    """Return only the explicitly configured, hash-bound private workbook."""
    value = os.environ.get(RNS_REAL_CORPUS_PATH)
    if value is None:
        raise RuntimeError("RNS_REAL_CORPUS_PATH is required for the real RNS corpus")
    if type(value) is not str or not value:
        raise RuntimeError("RNS_REAL_CORPUS_PATH must be a non-empty string")
    try:
        path = Path(value)
    except ValueError as error:
        raise RuntimeError("RNS_REAL_CORPUS_PATH must be an absolute regular file") from error
    if not path.is_absolute():
        raise RuntimeError("RNS_REAL_CORPUS_PATH must be an absolute regular file")
    if path.is_symlink():
        raise RuntimeError("RNS_REAL_CORPUS_PATH must not be a symlink")
    try:
        mode = path.stat().st_mode
    except OSError as error:
        raise RuntimeError("RNS_REAL_CORPUS_PATH must name an existing regular file") from error
    if not stat.S_ISREG(mode):
        raise RuntimeError("RNS_REAL_CORPUS_PATH must name an existing regular file")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != REAL_RNS_CORPUS_SHA256:
        raise RuntimeError("RNS_REAL_CORPUS_PATH SHA-256 does not match the real RNS corpus")
    return path
