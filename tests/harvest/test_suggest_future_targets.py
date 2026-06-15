"""Tests for harvest automation helpers."""

from __future__ import annotations

from scripts.harvest.harvest_presets import LLM_FIXTURES
from scripts.harvest.suggest_future_targets import (
    _draft_from_record,
    _eligible,
    _infer_expected_fragments,
    _tracking_slug,
)


def test_eligible_for_coverage_gap() -> None:
    record = {"trigger": {"kinds": ["coverage_gap"], "unhandled": []}}
    assert _eligible(record)


def test_infer_expected_fragments_from_diff() -> None:
    diff = """\
--- x.java (skeleton)
+++ x.java (llm)
@@
-        pass
+        assert value > 0, "must be positive"
"""
    assert _infer_expected_fragments({"diff_excerpt": diff}) == (
        'assert value > 0, "must be positive"',
    )


def test_draft_from_record_builds_tracking_id() -> None:
    record = {
        "source_path": str(LLM_FIXTURES / "MultiDimArray.java"),
        "trigger": {
            "kinds": ["coverage_gap"],
            "unhandled": [{"reason": "unsupported expression array_creation_expression"}],
        },
        "diff_excerpt": "+        return [[0] * cols for _ in range(rows)]",
        "repair_signals": ["todo-placeholder-removed"],
    }
    draft = _draft_from_record(record)
    assert draft is not None
    assert draft.tracking == "llm-harvest-multi-dim-array"
    assert draft.fixture_root_var == "LLM_FIXTURES"


def test_tracking_slug_splits_camel_case() -> None:
    assert _tracking_slug("AssertProbe") == "assert-probe"
    assert _tracking_slug("MultiDimArray") == "multi-dim-array"
