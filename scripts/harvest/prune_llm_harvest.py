#!/usr/bin/env python3
"""Compact the local LLM harvest log (dedupe by source path)."""

from __future__ import annotations

import argparse
from pathlib import Path

from j2py.llm.harvest import compact_harvest_records, harvest_records_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Harvest jsonl (default: .j2py/harvest/records.jsonl)",
    )
    parser.add_argument(
        "--keep-resolved",
        action="store_true",
        help="Keep rows with status=resolved (default: drop them)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts only; do not rewrite the file",
    )
    args = parser.parse_args()

    path = args.path or harvest_records_path()
    before, after = compact_harvest_records(
        path,
        drop_resolved=not args.keep_resolved,
        dry_run=args.dry_run,
    )
    if before == 0:
        print(f"No harvest records at {path}")
        return 0

    action = "would keep" if args.dry_run else "kept"
    print(f"{action} {after} of {before} records at {path}")
    if before > after:
        print(f"removed {before - after} duplicate or resolved rows")
    else:
        print("nothing to prune")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
