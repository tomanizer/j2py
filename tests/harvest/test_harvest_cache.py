"""Tests for harvest content cache (skip re-submitting unchanged sources)."""

from __future__ import annotations

from pathlib import Path

import pytest

from j2py.llm.harvest import write_harvest_records
from scripts.harvest import run_llm_harvest as harvest
from scripts.harvest.harvest_cache import (
    HarvestCacheEntry,
    load_harvest_cache,
    should_skip_harvest,
    sync_queue_offset,
)


def test_should_skip_when_hash_matches(tmp_path: Path) -> None:
    source = tmp_path / "A.java"
    source.write_text("class A {}", encoding="utf-8")
    digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    cache = {
        str(source.resolve()): HarvestCacheEntry(
            source_path=str(source.resolve()),
            java_sha256=digest,
            status="open",
        )
    }
    assert should_skip_harvest(source, cache)


def test_should_not_skip_when_content_changed(tmp_path: Path) -> None:
    source = tmp_path / "A.java"
    source.write_text("class A {}", encoding="utf-8")
    cache = {
        str(source.resolve()): HarvestCacheEntry(
            source_path=str(source.resolve()),
            java_sha256="deadbeef",
            status="open",
        )
    }
    assert not should_skip_harvest(source, cache)


def test_load_harvest_cache_from_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    records = tmp_path / "records.jsonl"
    java = tmp_path / "Foo.java"
    java.write_text("class Foo {}", encoding="utf-8")
    digest = __import__("hashlib").sha256(java.read_bytes()).hexdigest()
    write_harvest_records(
        [
            {
                "source_path": str(java.resolve()),
                "java_sha256": digest,
                "status": "open",
            }
        ],
        records,
    )
    monkeypatch.setattr(
        "scripts.harvest.harvest_cache.harvest_records_path",
        lambda: records,
    )
    cache = load_harvest_cache(records)
    assert str(java.resolve()) in cache
    assert cache[str(java.resolve())].java_sha256 == digest


def test_sync_queue_offset_skips_cached_prefix(tmp_path: Path) -> None:
    a = tmp_path / "a.java"
    b = tmp_path / "b.java"
    a.write_text("class A {}", encoding="utf-8")
    b.write_text("class B {}", encoding="utf-8")
    digest_a = __import__("hashlib").sha256(a.read_bytes()).hexdigest()
    cache = {
        str(a.resolve()): HarvestCacheEntry(str(a.resolve()), digest_a, "open"),
    }
    assert sync_queue_offset([a, b], cache, 0) == 1


def test_run_harvest_skips_cached_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "Cached.java"
    source.write_text("class Cached {}", encoding="utf-8")
    digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()

    monkeypatch.setattr(
        harvest,
        "load_harvest_cache",
        lambda: {
            str(source.resolve()): HarvestCacheEntry(
                str(source.resolve()),
                digest,
                "open",
            )
        },
    )
    monkeypatch.setattr(harvest, "begin_usage_session", lambda: None)
    monkeypatch.setattr(harvest, "resolve_model", lambda _p, _m: "test-model")
    monkeypatch.setattr(
        harvest,
        "translate_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not translate")),
    )

    used, skipped = harvest.run_harvest(
        [source],
        provider="gemini",
        model=None,
        validate=True,
        sleep_seconds=0.0,
        skip_cached=True,
    )
    assert used == 0
    assert skipped == 1
