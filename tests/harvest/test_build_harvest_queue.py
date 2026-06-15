"""Tests for harvest queue builder."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.harvest.build_harvest_queue import (
    _is_tier_a,
    collect_tier_a_entries,
    queue_is_stale,
    render_queue,
)


def test_is_tier_a_filters_correctly() -> None:
    assert _is_tier_a(
        {
            "path": "/x/Foo.java",
            "parse_ok": True,
            "syntax_ok": False,
            "coverage": 1.0,
            "unhandled_count": 0,
        }
    )
    assert not _is_tier_a(
        {
            "path": "/x/package-info.java",
            "parse_ok": True,
            "syntax_ok": False,
            "coverage": 1.0,
            "unhandled_count": 0,
        }
    )
    assert not _is_tier_a(
        {
            "path": "/x/Gap.java",
            "parse_ok": True,
            "syntax_ok": True,
            "coverage": 1.0,
            "unhandled_count": 0,
        }
    )


def test_collect_tier_a_entries_deduplicates_and_sorts(tmp_path: Path) -> None:
    java_path = tmp_path / "Small.java"
    java_path.write_text("class Small {}\n", encoding="utf-8")
    report = {
        "metadata": {"preset": "demo-dense"},
        "files": [
            {
                "path": str(java_path),
                "parse_ok": True,
                "syntax_ok": False,
                "coverage": 1.0,
                "unhandled_count": 0,
            },
            {
                "path": str(java_path),
                "parse_ok": True,
                "syntax_ok": False,
                "coverage": 1.0,
                "unhandled_count": 0,
            },
        ],
    }
    reports_dir = tmp_path / "corpus-reports"
    reports_dir.mkdir()
    (reports_dir / "demo-dense.json").write_text(json.dumps(report), encoding="utf-8")

    entries, used = collect_tier_a_entries(reports_dir)
    assert len(entries) == 1
    assert entries[0].preset == "demo-dense"
    assert any("demo-dense.json" in item for item in used)


def test_queue_is_stale_when_report_newer(tmp_path: Path) -> None:
    queue = tmp_path / "queue.txt"
    queue.write_text("# queue\n", encoding="utf-8")
    report = tmp_path / "report.json"
    report.write_text("{}", encoding="utf-8")
    report.touch()
    assert queue_is_stale(queue, [report], force=False)


def test_render_queue_includes_paths(tmp_path: Path) -> None:
    from scripts.harvest.build_harvest_queue import QueueEntry

    text = render_queue(
        [QueueEntry(preset="demo", path="/abs/A.java", loc=3)],
        corpus_root=tmp_path / ".corpus",
    )
    assert "/abs/A.java" in text
    assert "Tier A harvest queue" in text
