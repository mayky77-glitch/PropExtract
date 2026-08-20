#!/usr/bin/env python3
"""Build the sanitized, deterministic construction-registry seed artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rns_import_server.registry_storage import RegistryStorage, SCHEMA_VERSION, SEED_REVISION, sha256_file


ENTRIES = (
    {"seed_entry_id": "cgr-v1-051-2006437", "code_prefix": "051-2006437", "official_name": "Реконструкция УПГ-102 Ковыктинского ГКМ", "status": "active"},
    {"seed_entry_id": "cgr-v1-051-2006735", "code_prefix": "051-2006735", "official_name": "Газопровод подключения Тас-Юряхского и Верхневилючанского месторождений к МГ \"Сила Сибири\"", "status": "active"},
    {"seed_entry_id": "cgr-v1-051-2004430", "code_prefix": "051-2004430", "official_name": "Магистральный газопровод \"Сила Сибири\". Участок \"Ковыкта - Чаянда\"", "status": "active"},
    {"seed_entry_id": "cgr-v1-051-2000714", "code_prefix": "051-2000714", "official_name": "Обустройство Ковыктинского газоконденсатного месторождения", "status": "active"},
)


def build(output: Path, manifest: Path, *, check: bool = False) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        candidate = Path(directory) / output.name
        storage = RegistryStorage.create_seed(candidate, ENTRIES, seed_revision=SEED_REVISION)
        storage.close()
        payload = {
            "entry_count": len(ENTRIES),
            "schema_version": SCHEMA_VERSION,
            "seed_revision": SEED_REVISION,
            "sha256": sha256_file(candidate),
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        same = output.is_file() and manifest.is_file() and output.read_bytes() == candidate.read_bytes() and manifest.read_text(encoding="utf-8") == encoded
        if check:
            return same
        candidate.replace(output)
        manifest.write_text(encoded, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("rns_import_server/data/construction_registry.seed.sqlite3"))
    parser.add_argument("--manifest", type=Path, default=Path("rns_import_server/data/construction_registry.seed.manifest.json"))
    args = parser.parse_args()
    if not build(args.output, args.manifest, check=args.check):
        raise SystemExit("construction registry seed or manifest is not deterministic/current")


if __name__ == "__main__":
    main()
