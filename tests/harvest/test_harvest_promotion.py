"""Tests for harvest promotion and triage helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.harvest.harvest_state import HarvestState, load_state, save_state
from scripts.harvest.promote_harvest_signals import draft_issues, render_issue_body
from scripts.harvest.signal_patterns import grouped_rank, primary_signal
from scripts.harvest.triage_lib import (
    aggregate_signal_evidence,
    is_clean_harvest_path,
)


def test_is_clean_harvest_path() -> None:
    assert not is_clean_harvest_path("/var/folders/x/pytest-of-u/pytest-0/Foo.java")
    assert is_clean_harvest_path("/repo/tests/fixtures/llm/AssertProbe.java")


def test_primary_signal_groups_related() -> None:
    assert primary_signal("generic-typevar") == "protocol-stub"
    assert primary_signal("overload-dispatch") == "overload-runtime-to-typing"


def test_grouped_rank_deduplicates() -> None:
    ranked = grouped_rank(
        ["generic-typevar", "protocol-stub", "todo-placeholder-removed", "jdk-import-removed"]
    )
    assert ranked == ["protocol-stub", "todo-placeholder-removed"]


def test_render_issue_body_includes_pattern_family() -> None:
    from scripts.harvest.triage_lib import SignalEvidence

    body = render_issue_body(
        SignalEvidence(
            signal="unsupported-stmt-removed",
            count=2,
            sources=("tests/fixtures/llm/AssertProbe.java",),
            minimal_fixture="tests/fixtures/llm/AssertProbe.java",
            diagnostics=("unsupported statement assert_statement",),
        ),
        "unsupported-stmt-removed",
    )
    assert "Pattern family" in body
    assert "AssertProbe.java" in body
    assert "Anti-patterns" in body


def test_draft_issues_skips_filed_signals(monkeypatch) -> None:
    from scripts.harvest.harvest_state import FiledSignal
    from scripts.harvest.triage_lib import SignalEvidence

    monkeypatch.setattr(
        "scripts.harvest.promote_harvest_signals._gh_issue_exists",
        lambda _tag: False,
    )

    state = HarvestState(
        filed_signals={
            "unsupported-stmt-removed": FiledSignal(
                signal="unsupported-stmt-removed",
                issue_number=1,
                issue_url="",
                filed_at="",
                title="t",
            )
        }
    )
    evidence = [
        SignalEvidence(
            signal="unsupported-stmt-removed",
            count=1,
            sources=("a.java",),
            minimal_fixture="a.java",
            diagnostics=(),
        ),
        SignalEvidence(
            signal="todo-placeholder-removed",
            count=1,
            sources=("b.java",),
            minimal_fixture="b.java",
            diagnostics=(),
        ),
    ]
    drafts = draft_issues(evidence, limit=3, state=state)
    assert len(drafts) == 1
    assert drafts[0].signal == "todo-placeholder-removed"


def test_draft_issues_skips_open_github_issues(monkeypatch) -> None:
    from scripts.harvest.triage_lib import SignalEvidence

    def fake_gh(tag: str) -> bool:
        return tag == "harvest: protocol-stub"

    monkeypatch.setattr(
        "scripts.harvest.promote_harvest_signals._gh_issue_exists",
        fake_gh,
    )
    evidence = [
        SignalEvidence(
            signal="protocol-stub",
            count=3,
            sources=("a.java",),
            minimal_fixture="a.java",
            diagnostics=(),
        ),
        SignalEvidence(
            signal="adapter-class-introduced",
            count=2,
            sources=("b.java",),
            minimal_fixture="b.java",
            diagnostics=(),
        ),
    ]
    drafts = draft_issues(evidence, limit=1, state=HarvestState())
    assert len(drafts) == 1
    assert drafts[0].signal == "adapter-class-introduced"


def test_harvest_state_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = HarvestState(queue_total=5, harvest_offset=2)
    save_state(state, path)
    loaded = load_state(path)
    assert loaded.queue_total == 5
    assert loaded.harvest_offset == 2


def test_aggregate_signal_evidence(tmp_path: Path, monkeypatch) -> None:
    from scripts.harvest.harvest_presets import REPO_ROOT

    records = [
        {
            "source_path": str(REPO_ROOT / "tests/fixtures/llm/AssertProbe.java"),
            "repair_signals": ["unsupported-stmt-removed"],
            "trigger": {
                "unhandled": [{"reason": "unsupported statement assert_statement"}],
            },
        }
    ]
    evidence = aggregate_signal_evidence(records, repo_root=REPO_ROOT)
    assert evidence[0].signal == "unsupported-stmt-removed"
    assert evidence[0].count == 1
