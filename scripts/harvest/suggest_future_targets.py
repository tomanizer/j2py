#!/usr/bin/env python3
"""Suggest FUTURE_TARGETS entries from coverage-gap harvest records."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.harvest.aggregate_llm_harvest import _load_records
from scripts.harvest.harvest_presets import REPO_ROOT
from scripts.harvest.triage_lib import repair_signals, trigger_kinds

TARGETS_FILE = REPO_ROOT / "tests" / "targets" / "test_translation_targets.py"
LLM_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "llm"
CORPUS_CONSTRUCTS = REPO_ROOT / "tests" / "fixtures" / "corpus" / "constructs"
TARGET_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "java" / "targets"
DRAFT_DIR = REPO_ROOT / "scripts" / "harvest" / "drafts"

_TRACKING_RE = re.compile(r'tracking="([^"]+)"')


@dataclass(frozen=True)
class FutureTargetDraft:
    fixture: str
    fixture_root_var: str
    tracking: str
    reason: str
    expected_fragments: tuple[str, ...]
    source_path: str


def _existing_tracking_ids() -> set[str]:
    if not TARGETS_FILE.is_file():
        return set()
    return set(_TRACKING_RE.findall(TARGETS_FILE.read_text(encoding="utf-8")))


def _eligible(record: dict[str, object]) -> bool:
    if "coverage_gap" in trigger_kinds(record):
        return True
    trigger = record.get("trigger")
    if not isinstance(trigger, dict):
        return False
    unhandled = trigger.get("unhandled")
    return isinstance(unhandled, list) and len(unhandled) > 0


def _fixture_root_var(source_path: str) -> str:
    path = Path(source_path).resolve()
    roots = {
        "LLM_FIXTURES": LLM_FIXTURES.resolve(),
        "CORPUS_CONSTRUCT_FIXTURES": CORPUS_CONSTRUCTS.resolve(),
        "TARGET_FIXTURES": TARGET_FIXTURES.resolve(),
    }
    for name, root in roots.items():
        if path.parent == root:
            return name
    return "Path(...)  # TODO: set fixture_root manually"


def _infer_expected_fragments(record: dict[str, object]) -> tuple[str, ...]:
    diff = record.get("diff_excerpt")
    if not isinstance(diff, str):
        return ()
    fragments: list[str] = []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].strip()
        if not content or content.startswith("#"):
            continue
        if content.startswith("assert "):
            fragments.append(content)
        elif "return " in content and ("[[" in content or "for _ in range" in content):
            fragments.append(content.removeprefix("return ").strip())
        elif content.startswith("def ") or content.startswith("class "):
            continue
    return tuple(dict.fromkeys(fragments))


def _infer_reason(record: dict[str, object]) -> str:
    trigger = record.get("trigger")
    if isinstance(trigger, dict):
        unhandled = trigger.get("unhandled")
        if isinstance(unhandled, list) and unhandled:
            first = unhandled[0]
            if isinstance(first, dict):
                reason = first.get("reason")
                if isinstance(reason, str) and reason:
                    return reason
    signals = repair_signals(record)
    if signals:
        return f"Rule-layer gap; LLM repair signal: {signals[0]}"
    return "Rule-layer gap promoted from LLM harvest"


def _draft_from_record(record: dict[str, object]) -> FutureTargetDraft | None:
    source_path = record.get("source_path")
    if not isinstance(source_path, str):
        return None
    path = Path(source_path)
    expected = _infer_expected_fragments(record)
    if not expected:
        return None
    tracking = f"llm-harvest-{_tracking_slug(path.stem)}"
    return FutureTargetDraft(
        fixture=path.name,
        fixture_root_var=_fixture_root_var(source_path),
        tracking=tracking,
        reason=_infer_reason(record),
        expected_fragments=expected,
        source_path=source_path,
    )


def _tracking_slug(stem: str) -> str:
    split_camel = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", stem)
    return split_camel.lower().replace("_", "-")


def _render_draft(draft: FutureTargetDraft) -> str:
    expected = ", ".join(repr(item) for item in draft.expected_fragments)
    return f"""    TranslationTarget(
        fixture="{draft.fixture}",
        fixture_root={draft.fixture_root_var},
        tracking="{draft.tracking}",
        reason="{draft.reason}",
        expected_fragments=({expected},),
    ),"""


def _latest_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    from j2py.llm.harvest import latest_harvest_records

    return latest_harvest_records(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Harvest jsonl (default: .j2py/harvest/records.jsonl)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write snippet to scripts/harvest/drafts/future_targets_snippet.py",
    )
    args = parser.parse_args()

    from j2py.llm.harvest import harvest_records_path

    path = args.path or harvest_records_path()
    records = _latest_records(_load_records(path))
    existing = _existing_tracking_ids()

    drafts: list[FutureTargetDraft] = []
    for record in records:
        if record.get("status") == "resolved":
            continue
        if not _eligible(record):
            continue
        draft = _draft_from_record(record)
        if draft is None:
            continue
        if not draft.expected_fragments:
            print(f"skip (no expected fragment inferred): {draft.source_path}")
            continue
        if draft.tracking in existing:
            print(f"skip (already in FUTURE_TARGETS): {draft.tracking}")
            continue
        drafts.append(draft)

    if not drafts:
        print("No new coverage-gap records eligible for FUTURE_TARGETS.")
        return 0

    snippet = "(\n" + "\n".join(_render_draft(d) for d in drafts) + "\n)"
    print(f"Suggested FUTURE_TARGETS additions ({len(drafts)}):\n")
    print(snippet)

    if args.write:
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        out = DRAFT_DIR / "future_targets_snippet.py"
        body = (
            '"""Draft FUTURE_TARGETS entries — review before merging into '
            'tests/targets/test_translation_targets.py."""\n\n'
            f"FUTURE_TARGETS_DRAFT = {snippet}\n"
        )
        out.write_text(body, encoding="utf-8")
        print(f"\nWrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
