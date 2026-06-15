"""Tests for LLM harvest heuristics and record shape."""

from __future__ import annotations

import json
from pathlib import Path

from j2py.llm.harvest import (
    build_harvest_record,
    compact_harvest_records,
    infer_repair_signals,
    latest_harvest_records,
    load_harvest_records,
    record_llm_repair,
    write_harvest_records,
)
from j2py.translate.diagnostics import TranslationDiagnostics


def test_infer_repair_signals_detects_protocol_and_typevar() -> None:
    skeleton = "class InterfaceDefaults(Protocol):\n    def handle(self, value: T) -> None: ...\n"
    final = (
        "from typing import Protocol, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Consumer(Protocol[T]):\n    def accept(self, value: T) -> None: ...\n"
    )
    signals = infer_repair_signals(skeleton=skeleton, final=final)
    assert "protocol-stub" in signals
    assert "generic-typevar" in signals


def test_infer_repair_signals_detects_overload_dispatch() -> None:
    skeleton = "from j2py_runtime import overloaded\n@overloaded\ndef get_instance(x: str): ...\n"
    final = "import typing\n@typing.overload\ndef get_instance(x: str, /) -> object: ...\n"
    signals = infer_repair_signals(skeleton=skeleton, final=final)
    assert "overload-dispatch" in signals
    assert "overload-runtime-to-typing" in signals


def test_build_harvest_record_includes_trigger_and_diff(tmp_path: Path) -> None:
    diagnostics = TranslationDiagnostics()
    record = build_harvest_record(
        source_path=tmp_path / "Example.java",
        java_source="public class Example {}",
        skeleton="class Example:\n    pass\n",
        final_python="class Example:\n    def run(self) -> None:\n        pass\n",
        model="claude-sonnet-4-6",
        coverage=1.0,
        diagnostics=diagnostics,
        pre_validation=None,
        structural_verification=None,
    )
    assert record.schema_version == "1"
    assert record.trigger.kinds == ("unknown",)
    assert "class Example" in record.diff_excerpt


def test_record_llm_repair_appends_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("J2PY_LLM_HARVEST", "1")
    monkeypatch.setenv("J2PY_LLM_HARVEST_PATH", str(tmp_path / "records.jsonl"))
    path = record_llm_repair(
        source_path=tmp_path / "Probe.java",
        java_source="public class Probe {}",
        skeleton="# TODO(j2py): unsupported assert_statement\npass\n",
        final_python="assert True\n",
        model="claude-sonnet-4-6",
        coverage=0.5,
        diagnostics=TranslationDiagnostics(),
        pre_validation=None,
        structural_verification=None,
        repo_root=tmp_path,
    )
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["source_path"].endswith("Probe.java")
    assert "unsupported-stmt-removed" in payload["repair_signals"]


def test_compact_harvest_records_keeps_latest_per_source(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    write_harvest_records(
        [
            {"source_path": "/a/Foo.java", "recorded_at": "t1", "status": "open"},
            {"source_path": "/a/Foo.java", "recorded_at": "t2", "status": "open"},
            {"source_path": "/a/Bar.java", "recorded_at": "t1", "status": "resolved"},
        ],
        path,
    )
    before, after = compact_harvest_records(path, drop_resolved=True)
    assert before == 3
    assert after == 1
    remaining = load_harvest_records(path)
    assert len(remaining) == 1
    assert remaining[0]["source_path"] == "/a/Foo.java"
    assert remaining[0]["recorded_at"] == "t2"


def test_latest_harvest_records_dedupes_by_source() -> None:
    records = [
        {"source_path": "/x/A.java", "n": 1},
        {"source_path": "/x/A.java", "n": 2},
        {"source_path": "/x/B.java", "n": 1},
    ]
    latest = latest_harvest_records(records)
    assert len(latest) == 2
    assert next(item for item in latest if item["source_path"].endswith("A.java"))["n"] == 2
