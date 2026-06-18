"""Report serialization helpers for corpus scoreboards."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any


def report_payload(
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: Iterable[Any],
) -> dict[str, Any]:
    return {
        "metadata": metadata,
        "summary": summary,
        "files": [asdict(metric) for metric in metrics],
    }


def write_json_report(
    path: Path,
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: Iterable[Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report_payload(metadata=metadata, summary=summary, metrics=metrics)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv_report(path: Path, metrics: Iterable[Any], *, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for metric in metrics:
            writer.writerow(asdict(metric))
