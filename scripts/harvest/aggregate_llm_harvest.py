#!/usr/bin/env python3
"""Aggregate local LLM harvest records into a rule-layer triage report."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from j2py.llm.harvest import harvest_records_path, latest_harvest_records, load_harvest_records
from scripts.harvest.triage_lib import repair_signals, trigger_kinds


def _load_records(path: Path) -> list[dict[str, object]]:
    return load_harvest_records(path)


def _mypy_error_prefix(error: str) -> str:
    if " is not defined" in error:
        return "undefined-name"
    if "no-redef" in error:
        return "overload-redef"
    if "Protocol" in error or "type-arg" in error:
        return "typing-protocol"
    if "no-untyped-def" in error:
        return "missing-annotation"
    return "other-mypy"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Harvest jsonl path (default: .j2py/harvest/records.jsonl)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Max rows per ranked section",
    )
    args = parser.parse_args()

    path = args.path or harvest_records_path()
    records = latest_harvest_records(_load_records(path))
    if not records:
        print(f"No harvest records at {path}")
        print("Run a translation with LLM enabled (make test-llm-e2e or j2py translate).")
        return 0

    signal_counts: Counter[str] = Counter()
    trigger_counts: Counter[str] = Counter()
    mypy_counts: Counter[str] = Counter()
    open_by_signal: dict[str, list[str]] = {}

    for record in records:
        if record.get("status") == "resolved":
            continue
        source = str(record.get("source_path", "?"))
        for kind in trigger_kinds(record):
            trigger_counts[kind] += 1
        for signal in repair_signals(record):
            signal_counts[signal] += 1
            open_by_signal.setdefault(signal, []).append(source)
        trigger = record.get("trigger")
        if isinstance(trigger, dict):
            errors = trigger.get("pre_validation_errors")
            if isinstance(errors, list):
                for error in errors:
                    if isinstance(error, str):
                        mypy_counts[_mypy_error_prefix(error)] += 1

    print(f"LLM harvest report ({len(records)} unique sources) — {path}\n")

    print("Trigger kinds (why LLM ran):")
    for kind, count in trigger_counts.most_common(args.top):
        print(f"  {count:4d}  {kind}")

    print("\nRepair signals (what LLM changed — rule-layer candidates):")
    for signal, count in signal_counts.most_common(args.top):
        print(f"  {count:4d}  {signal}")

    print("\nPre-LLM validation error buckets:")
    for bucket, count in mypy_counts.most_common(args.top):
        print(f"  {count:4d}  {bucket}")

    print("\nExample files by repair signal:")
    for signal, _count in signal_counts.most_common(min(8, args.top)):
        examples = open_by_signal.get(signal, [])[:3]
        if examples:
            print(f"  {signal}:")
            for example in examples:
                print(f"    - {example}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
