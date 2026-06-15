"""Pinned file sets for automated LLM harvest runs."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LLM_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "llm"
CORPUS_CONSTRUCTS = REPO_ROOT / "tests" / "fixtures" / "corpus" / "constructs"

# Cheap local probes — no external corpus checkout required.
LOCAL_PROBE_PATHS: tuple[Path, ...] = tuple(sorted(LLM_FIXTURES.glob("*.java")))

# Construct fixtures that typically need LLM mypy repair (rule layer coverage == 1.0).
CORPUS_MYPY_PROBE_PATHS: tuple[Path, ...] = (
    CORPUS_CONSTRUCTS / "AdvancedStreams.java",
    CORPUS_CONSTRUCTS / "AnonymousAndInner.java",
    CORPUS_CONSTRUCTS / "InterfaceDefaults.java",
)

HARVEST_PRESETS: dict[str, tuple[Path, ...]] = {
    "local": LOCAL_PROBE_PATHS,
    "constructs": LOCAL_PROBE_PATHS + CORPUS_MYPY_PROBE_PATHS,
}

DEFAULT_HARVEST_PRESET = "local"
