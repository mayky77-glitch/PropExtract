"""Build the deterministic app-local Python tree used by Windows installs."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ARTIFACT_HASHES = {
    "windows/python-3.12.10-embed-amd64.zip": "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3",
    "python/openpyxl-3.1.5-py2.py3-none-any.whl": "5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2",
    "python/et_xmlfile-2.0.0-py3-none-any.whl": "7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise RuntimeError(f"unsafe archive member: {member.filename}")
        archive.extractall(destination)


def directory_digest(root: Path) -> tuple[str, int]:
    entries = sorted(
        (path.relative_to(root).as_posix(), file_sha256(path))
        for path in root.rglob("*")
        if path.is_file()
    )
    canonical = "".join(f"{digest}  {relative}\n" for relative, digest in entries).encode()
    return hashlib.sha256(canonical).hexdigest(), len(entries)


def build(packages: Path, template: Path, output: Path) -> tuple[str, int]:
    if output.exists():
        raise RuntimeError(f"output already exists: {output}")
    for filename, expected in ARTIFACT_HASHES.items():
        actual = file_sha256(packages / filename)
        if actual != expected:
            raise RuntimeError(f"unexpected SHA-256 for {filename}: {actual}")

    output.mkdir(parents=True)
    extract(packages / "windows" / "python-3.12.10-embed-amd64.zip", output)
    site_packages = output / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    extract(packages / "python" / "openpyxl-3.1.5-py2.py3-none-any.whl", site_packages)
    extract(packages / "python" / "et_xmlfile-2.0.0-py3-none-any.whl", site_packages)
    (output / "python312._pth").write_bytes(template.read_bytes())
    return directory_digest(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    digest, count = build(arguments.packages, arguments.template, arguments.output)
    print(json.dumps({"sha256": digest, "files": count}, sort_keys=True))


if __name__ == "__main__":
    main()
