"""Shared LLM harvest triage helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from j2py.llm.harvest import latest_harvest_records, load_harvest_records

TEMP_PATH_MARKERS = ("/pytest-", "/tmp/pytest", "/var/folders/")


def is_clean_harvest_path(path: str) -> bool:
    """Return False for pytest temp dirs that pollute triage."""
    return not any(marker in path for marker in TEMP_PATH_MARKERS)


def repair_signals(record: dict[str, object]) -> tuple[str, ...]:
    signals = record.get("repair_signals")
    if isinstance(signals, list):
        return tuple(str(item) for item in signals)
    return ()


def trigger_kinds(record: dict[str, object]) -> tuple[str, ...]:
    trigger = record.get("trigger")
    if not isinstance(trigger, dict):
        return ("unknown",)
    kinds = trigger.get("kinds")
    if isinstance(kinds, list):
        return tuple(str(item) for item in kinds)
    return ("unknown",)


def load_open_records(path: Path | None = None) -> list[dict[str, object]]:
    """Latest record per source, excluding resolved and pytest temp paths."""
    records_path = path
    if records_path is None:
        from j2py.llm.harvest import harvest_records_path

        records_path = harvest_records_path()
    records = latest_harvest_records(load_harvest_records(records_path))
    return [
        record
        for record in records
        if record.get("status") != "resolved"
        and is_clean_harvest_path(str(record.get("source_path", "")))
    ]


@dataclass(frozen=True)
class SignalEvidence:
    signal: str
    count: int
    sources: tuple[str, ...]
    minimal_fixture: str | None
    diagnostics: tuple[str, ...]


def _short_repo_path(path: str, repo_root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return path


def _pick_minimal_fixture(sources: tuple[str, ...], repo_root: Path) -> str | None:
    """Prefer tests/fixtures/llm, then corpus/constructs, then shortest path."""
    ranked = sorted(
        sources,
        key=lambda item: (
            0 if "/tests/fixtures/llm/" in item else 1,
            0 if "/tests/fixtures/corpus/constructs/" in item else 1,
            0 if "/tests/fixtures/java/" in item else 1,
            len(item),
        ),
    )
    if not ranked:
        return None
    return _short_repo_path(ranked[0], repo_root)


def _collect_diagnostics(records: list[dict[str, object]], signal: str) -> tuple[str, ...]:
    seen: list[str] = []
    for record in records:
        if signal not in repair_signals(record):
            continue
        trigger = record.get("trigger")
        if not isinstance(trigger, dict):
            continue
        unhandled = trigger.get("unhandled")
        if isinstance(unhandled, list):
            for item in unhandled:
                if isinstance(item, dict):
                    reason = item.get("reason")
                    if isinstance(reason, str) and reason and reason not in seen:
                        seen.append(reason)
        if len(seen) >= 5:
            break
    return tuple(seen)


def aggregate_signal_evidence(
    records: list[dict[str, object]],
    *,
    repo_root: Path,
) -> list[SignalEvidence]:
    """Rank repair signals with clean source paths."""
    by_signal: dict[str, list[str]] = {}
    for record in records:
        source = str(record.get("source_path", ""))
        for signal in repair_signals(record):
            by_signal.setdefault(signal, []).append(source)

    counts = Counter({signal: len(set(paths)) for signal, paths in by_signal.items()})
    evidence: list[SignalEvidence] = []
    for signal, count in counts.most_common():
        sources = tuple(sorted(set(by_signal[signal])))
        signal_records = [
            record
            for record in records
            if signal in repair_signals(record)
        ]
        evidence.append(
            SignalEvidence(
                signal=signal,
                count=count,
                sources=sources,
                minimal_fixture=_pick_minimal_fixture(sources, repo_root),
                diagnostics=_collect_diagnostics(signal_records, signal),
            )
        )
    return evidence
