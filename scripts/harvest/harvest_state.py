"""Persistent state for harvest queue progress and filed issue tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from scripts.harvest.harvest_presets import REPO_ROOT

STATE_SCHEMA_VERSION = 1
DEFAULT_STATE_PATH = REPO_ROOT / ".j2py" / "harvest" / "state.json"
DEFAULT_QUEUE_PATH = REPO_ROOT / ".j2py" / "harvest" / "queue.txt"


@dataclass
class FiledSignal:
    signal: str
    issue_number: int
    issue_url: str
    filed_at: str
    title: str


@dataclass
class HarvestState:
    schema_version: int = STATE_SCHEMA_VERSION
    queue_path: str = str(DEFAULT_QUEUE_PATH)
    queue_built_at: str | None = None
    queue_source_reports: list[str] = field(default_factory=list)
    queue_total: int = 0
    harvest_offset: int = 0
    last_harvest_at: str | None = None
    last_promotion_at: str | None = None
    filed_signals: dict[str, FiledSignal] = field(default_factory=dict)

    @property
    def queue_remaining(self) -> int:
        return max(0, self.queue_total - self.harvest_offset)

    @property
    def queue_complete(self) -> bool:
        return self.queue_total > 0 and self.harvest_offset >= self.queue_total


def state_path(path: Path | None = None) -> Path:
    return path or DEFAULT_STATE_PATH


def load_state(path: Path | None = None) -> HarvestState:
    target = state_path(path)
    if not target.is_file():
        return HarvestState()
    payload = json.loads(target.read_text(encoding="utf-8"))
    filed: dict[str, FiledSignal] = {}
    raw_filed = payload.get("filed_signals", {})
    if isinstance(raw_filed, dict):
        for key, value in raw_filed.items():
            if isinstance(value, dict):
                filed[str(key)] = FiledSignal(
                    signal=str(value.get("signal", key)),
                    issue_number=int(value["issue_number"]),
                    issue_url=str(value.get("issue_url", "")),
                    filed_at=str(value.get("filed_at", "")),
                    title=str(value.get("title", "")),
                )
    return HarvestState(
        schema_version=int(payload.get("schema_version", STATE_SCHEMA_VERSION)),
        queue_path=str(payload.get("queue_path", str(DEFAULT_QUEUE_PATH))),
        queue_built_at=payload.get("queue_built_at"),
        queue_source_reports=list(payload.get("queue_source_reports", [])),
        queue_total=int(payload.get("queue_total", 0)),
        harvest_offset=int(payload.get("harvest_offset", 0)),
        last_harvest_at=payload.get("last_harvest_at"),
        last_promotion_at=payload.get("last_promotion_at"),
        filed_signals=filed,
    )


def save_state(state: HarvestState, path: Path | None = None) -> Path:
    target = state_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": state.schema_version,
        "queue_path": state.queue_path,
        "queue_built_at": state.queue_built_at,
        "queue_source_reports": state.queue_source_reports,
        "queue_total": state.queue_total,
        "harvest_offset": state.harvest_offset,
        "last_harvest_at": state.last_harvest_at,
        "last_promotion_at": state.last_promotion_at,
        "filed_signals": {
            key: {
                "signal": value.signal,
                "issue_number": value.issue_number,
                "issue_url": value.issue_url,
                "filed_at": value.filed_at,
                "title": value.title,
            }
            for key, value in state.filed_signals.items()
        },
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
