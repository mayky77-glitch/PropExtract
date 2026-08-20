#!/usr/bin/env python3
"""Validate the checked-in construction registry seed without modifying it."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rns_import_server.registry_storage import validate_seed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, default=Path("rns_import_server/data/construction_registry.seed.sqlite3"))
    parser.add_argument("--manifest", type=Path, default=Path("rns_import_server/data/construction_registry.seed.manifest.json"))
    args = parser.parse_args()
    manifest = validate_seed(args.seed, args.manifest)
    print(f"ok schema={manifest['schema_version']} revision={manifest['seed_revision']} entries={manifest['entry_count']}")


if __name__ == "__main__":
    main()
