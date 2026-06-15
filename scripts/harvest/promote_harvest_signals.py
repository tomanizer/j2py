"""Create pattern-family GitHub issues from LLM harvest triage."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.harvest.harvest_presets import REPO_ROOT
from scripts.harvest.harvest_state import (
    FiledSignal,
    HarvestState,
    load_state,
    save_state,
    utc_now_iso,
)
from scripts.harvest.signal_patterns import PATTERN_BY_SIGNAL, grouped_rank, primary_signal
from scripts.harvest.triage_lib import SignalEvidence, aggregate_signal_evidence, load_open_records


@dataclass(frozen=True)
class IssueDraft:
    signal: str
    title: str
    body: str
    labels: tuple[str, ...] = ("enhancement", "rule-layer")


def _short_path(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return path


def _role_for_source(source: str, minimal: str | None) -> str:
    short = _short_path(source)
    if minimal and short == minimal:
        return "Minimal fixture"
    if "/tests/fixtures/llm/" in source:
        return "LLM probe fixture"
    if "/tests/fixtures/corpus/constructs/" in source:
        return "Construct fixture"
    if "/tests/fixtures/java/" in source:
        return "Target fixture"
    if "/.corpus/" in source:
        return "Corpus evidence (extract minimal repro if large)"
    return "Regression peer"


def render_issue_body(evidence: SignalEvidence, pattern_key: str) -> str:
    pattern = PATTERN_BY_SIGNAL.get(pattern_key)
    if pattern is None:
        pattern = PATTERN_BY_SIGNAL["todo-placeholder-removed"]

    minimal = evidence.minimal_fixture
    rows: list[str] = []
    for source in evidence.sources[:12]:
        rows.append(f"| `{_short_path(source)}` | {_role_for_source(source, minimal)} |")
    if len(evidence.sources) > 12:
        rows.append(f"| … | {len(evidence.sources) - 12} more in harvest records |")

    diagnostic_block = ""
    if evidence.diagnostics:
        diagnostic_block = "\n**Sample rule-layer diagnostics:**\n```\n"
        diagnostic_block += "\n".join(evidence.diagnostics[:5])
        diagnostic_block += "\n```\n"

    return f"""## Pattern family (not a single-file fix)

**Family:** {pattern.family}

**Do not** special-case one fixture filename. Implement the general rule for the whole
pattern class.

## Mechanism

| Layer | Detail |
|-------|--------|
| AST / diagnostic | {pattern.ast_or_diagnostic} |
| Harvest signal(s) | {pattern.harvest_signals} |
| Translator home | {pattern.translator_home} |
| Mapping / policy | {pattern.mapping} |

## Harvest evidence ({evidence.count} clean sources)

| Source | Role |
|--------|------|
{chr(10).join(rows)}

{diagnostic_block}
## Acceptance criteria (pattern-level)

- [ ] **General rule** covers all instances of this pattern class in the evidence table
- [ ] **Minimal fixture** (if listed) passes without LLM / without this repair signal on re-harvest
- [ ] **Parametrised tests:** ≥2 variants of the pattern (not one fixture stem)
- [ ] **Regression peers:** evidence-table files improve on re-harvest
- [ ] `make check` green; update `FUTURE_TARGETS` only with pattern-level acceptance

## Anti-patterns (reject in review)

- Filename checks or fixture-name branching
- Copy-pasting one harvest `diff_excerpt` without a visitor/registry rule
- Fixing a single xfail while the general diagnostic remains

## Related issues

{pattern.related_issues}

## Out of scope

{pattern.out_of_scope}

## Verify

```bash
make check
make test-targets
make harvest-prune && make harvest-triage
grep '{evidence.signal}' .j2py/harvest/records.jsonl
```
"""


def _gh_issue_exists(title_fragment: str) -> bool:
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--search", title_fragment, "--state", "open", "--limit", "5"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return bool(result.stdout.strip())


def is_promotable_signal(primary: str, state: HarvestState) -> bool:
    """Return True when this pattern family can be drafted or filed."""
    if primary in state.filed_signals:
        return False
    if primary not in PATTERN_BY_SIGNAL:
        return False
    if _gh_issue_exists(f"harvest: {primary}"):
        return False
    return True


def draft_issues(
    evidence_list: list[SignalEvidence],
    *,
    limit: int,
    state: HarvestState,
) -> list[IssueDraft]:
    signal_order = grouped_rank([item.signal for item in evidence_list])
    evidence_by_primary = {primary_signal(item.signal): item for item in evidence_list}

    drafts: list[IssueDraft] = []
    for primary in signal_order:
        if len(drafts) >= limit:
            break
        if not is_promotable_signal(primary, state):
            continue
        evidence = evidence_by_primary.get(primary)
        if evidence is None:
            continue
        pattern = PATTERN_BY_SIGNAL[primary]
        drafts.append(
            IssueDraft(
                signal=primary,
                title=pattern.title,
                body=render_issue_body(evidence, primary),
            )
        )
    return drafts


def create_issues(
    drafts: list[IssueDraft],
    *,
    create: bool,
    state: HarvestState,
) -> list[FiledSignal]:
    filed: list[FiledSignal] = []
    for draft in drafts:
        if not create:
            print(f"\n--- DRAFT ISSUE: {draft.title} ---\n{draft.body}\n")
            continue
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                draft.title,
                "--label",
                "enhancement,rule-layer",
                "--body",
                draft.body,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        url = result.stdout.strip()
        issue_number = int(url.rstrip("/").split("/")[-1])
        record = FiledSignal(
            signal=draft.signal,
            issue_number=issue_number,
            issue_url=url,
            filed_at=utc_now_iso(),
            title=draft.title,
        )
        state.filed_signals[draft.signal] = record
        filed.append(record)
        print(f"Created #{issue_number}: {draft.title}")
        print(url)
    return filed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issues",
        type=int,
        default=3,
        help="Max pattern-family issues to draft or create (default: 3)",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create GitHub issues via gh (default: print drafts only)",
    )
    parser.add_argument(
        "--records",
        type=Path,
        default=None,
        help="Harvest records jsonl (default: .j2py/harvest/records.jsonl)",
    )
    args = parser.parse_args()

    records = load_open_records(args.records)
    if not records:
        print("No open harvest records. Run make harvest-run or make harvest-gemini first.")
        return 1

    evidence = aggregate_signal_evidence(records, repo_root=REPO_ROOT)
    state = load_state()
    drafts = draft_issues(evidence, limit=args.issues, state=state)

    if not drafts:
        print(
            "No new pattern families to promote "
            "(all ranked signals filed in state.json or open on GitHub)."
        )
        print("Signals in state:", ", ".join(sorted(state.filed_signals)) or "(none)")
        return 0

    create_issues(drafts, create=args.create, state=state)
    state.last_promotion_at = utc_now_iso()
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
