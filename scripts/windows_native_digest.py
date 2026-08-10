"""Calculate the canonical directory digest mirrored by Windows PowerShell."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_digest(root: Path) -> tuple[str, int]:
    entries = sorted(
        (path.relative_to(root).as_posix(), file_sha256(path))
        for path in root.rglob("*")
        if path.is_file()
    )
    canonical = "".join(f"{digest}  {relative}\n" for relative, digest in entries).encode()
    return hashlib.sha256(canonical).hexdigest(), len(entries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    arguments = parser.parse_args()
    digest, count = directory_digest(arguments.root)
    print(json.dumps({"sha256": digest, "files": count}, sort_keys=True))


if __name__ == "__main__":
    main()
