"""Workflow policy checks for draft PR CI behavior."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workflow_text(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_heavy_workflows_defer_jobs_for_draft_pull_requests() -> None:
    for workflow in ("corpus.yml", "behavior.yml"):
        text = _workflow_text(workflow)

        assert "types: [opened, synchronize, reopened, ready_for_review]" in text
        assert "github.event_name != 'pull_request' || !github.event.pull_request.draft" in text


def test_core_ci_still_runs_on_pull_requests() -> None:
    text = _workflow_text("ci.yml")

    assert "pull_request:" in text
    assert "github.event.pull_request.draft" not in text
