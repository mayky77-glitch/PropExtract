"""Build the deterministic portable Tesseract ZIP used by Windows installs."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
import zipfile
from pathlib import Path

UPSTREAM_SHA256 = "bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4"
FIXED_TIMESTAMP = (2026, 7, 24, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_file(archive: zipfile.ZipFile, source: Path, name: str) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, source.read_bytes())


def build(installer: Path, seven_zip: Path, output: Path) -> str:
    actual = sha256(installer)
    if actual != UPSTREAM_SHA256:
        raise RuntimeError(f"unexpected upstream SHA-256: {actual}")

    with tempfile.TemporaryDirectory(prefix="propextract-tesseract-") as temporary_name:
        extracted = Path(temporary_name) / "extracted"
        subprocess.run(
            [str(seven_zip), "x", "-y", f"-o{extracted}", str(installer)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        runtime_files = [extracted / "tesseract.exe", *sorted(extracted.glob("*.dll"))]
        documentation = {
            "licenses/tesseract/LICENSE": extracted / "doc" / "LICENSE",
            "licenses/tesseract/AUTHORS": extracted / "doc" / "AUTHORS",
            "licenses/tesseract/README.md": extracted / "doc" / "README.md",
        }
        missing = [path for path in [*runtime_files, *documentation.values()] if not path.is_file()]
        if missing:
            raise RuntimeError(f"missing extracted files: {missing}")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for source in runtime_files:
                add_file(archive, source, f"tesseract/{source.name}")
            for name, source in documentation.items():
                add_file(archive, source, name)
    return sha256(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--seven-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(build(arguments.installer, arguments.seven_zip, arguments.output))


if __name__ == "__main__":
    main()
