#!/usr/bin/env python3
"""End-to-end harvest promotion: queue → Gemini batch → prune → triage → GitHub issues."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from j2py.llm.harvest import compact_harvest_records, harvest_records_path
from scripts.harvest.build_harvest_queue import build_queue
from scripts.harvest.harvest_presets import REPO_ROOT
from scripts.harvest.harvest_state import save_state, utc_now_iso
from scripts.harvest.promote_harvest_signals import create_issues, draft_issues
from scripts.harvest.run_llm_harvest import run_harvest
from scripts.harvest.harvest_cache import load_harvest_cache, sync_queue_offset
from scripts.harvest.triage_lib import aggregate_signal_evidence, load_open_records

DEFAULT_QUEUE = REPO_ROOT / ".j2py" / "harvest" / "queue.txt"


def _print_triage(records_path: Path) -> None:
    aggregate = REPO_ROOT / "scripts/harvest/aggregate_llm_harvest.py"
    subprocess.run(
        [sys.executable, str(aggregate), "--path", str(records_path)],
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-queue",
        action="store_true",
        help="Force rebuild Tier A queue from corpus-reports/",
    )
    parser.add_argument(
        "--queue-only",
        action="store_true",
        help="Only build/refresh queue; skip harvest and issue promotion",
    )
    parser.add_argument(
        "--skip-harvest",
        action="store_true",
        help="Skip Gemini batch (prune, triage, and promote only)",
    )
    parser.add_argument(
        "--skip-local",
        action="store_true",
        help="Skip cheap local preset harvest before queue batch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2,
        help="Gemini queue batch size (default: 2 for free tier)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=-1,
        help="Queue offset (-1 = use state.json harvest_offset)",
    )
    parser.add_argument(
        "--issues",
        type=int,
        default=3,
        help="Pattern-family GitHub issues to draft/create (default: 3)",
    )
    parser.add_argument(
        "--create-issues",
        action="store_true",
        help="Create GitHub issues via gh (default: draft to stdout only)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-harvest paths even when records.jsonl has the same java_sha256",
    )
    parser.add_argument(
        "--no-skip-cached",
        action="store_true",
        help="Translate every queued path (ignore harvest content cache)",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        default=DEFAULT_QUEUE,
        help="Harvest queue file path",
    )
    args = parser.parse_args()

    queue_path, state, rebuilt = build_queue(
        queue_path=args.queue,
        force=args.refresh_queue,
    )
    if rebuilt:
        print(f"Queue rebuilt: {queue_path} ({state.queue_total} files)")
    else:
        print(f"Queue OK: {queue_path} ({state.queue_total} files, offset={state.harvest_offset})")

    if args.queue_only:
        save_state(state)
        return 0

    records_path = harvest_records_path()
    cache = load_harvest_cache(records_path)
    skip_cached = not args.no_skip_cached

    if not args.skip_local:
        print("\n== Local preset harvest (tests/fixtures/llm/) ==")
        from scripts.harvest.harvest_presets import HARVEST_PRESETS

        local_paths = list(HARVEST_PRESETS["local"])
        if local_paths:
            run_harvest(
                local_paths,
                provider="gemini",
                model=None,
                validate=True,
                sleep_seconds=0.0,
                skip_cached=skip_cached,
                force=args.force,
            )

    if not args.skip_harvest and state.queue_total > 0:
        from scripts.harvest.run_llm_harvest import load_paths_from_file, select_paths

        all_paths = load_paths_from_file(queue_path)
        if args.offset < 0 and skip_cached:
            synced = sync_queue_offset(all_paths, cache, state.harvest_offset)
            if synced != state.harvest_offset:
                print(
                    f"Synced queue offset {state.harvest_offset} → {synced} "
                    "(skipped already-recorded paths)"
                )
                state.harvest_offset = synced

        offset = state.harvest_offset if args.offset < 0 else args.offset
        if offset >= state.queue_total:
            print(
                f"\nQueue fully harvested (offset={offset}, total={state.queue_total}). "
                "Use --refresh-queue after new corpus scans or --skip-harvest to promote only."
            )
        elif args.limit > 0:
            from scripts.harvest.run_llm_harvest import load_paths_from_file, select_paths

            all_paths = load_paths_from_file(queue_path)
            batch = select_paths(
                all_paths,
                offset=offset,
                limit=args.limit,
                skip_temp_paths=True,
                skip_package_info=True,
            )
            if batch:
                print(f"\n== Gemini queue harvest offset={offset} limit={args.limit} ==")
                used, skipped = run_harvest(
                    batch,
                    provider="gemini",
                    model=None,
                    validate=True,
                    sleep_seconds=6.0,
                    skip_cached=skip_cached,
                    force=args.force,
                )
                print(f"Batch done: llm={used} skipped={skipped}")
                state.harvest_offset = offset + len(batch)
                state.last_harvest_at = utc_now_iso()

    before, after = compact_harvest_records(records_path, drop_resolved=True, dry_run=False)
    if before != after:
        print(f"Pruned harvest log: kept {after} of {before} records")

    print("\n== Triage ==")
    _print_triage(records_path)

    records = load_open_records(records_path)
    if not records:
        print("\nNo records to promote.")
        save_state(state)
        return 0

    evidence = aggregate_signal_evidence(records, repo_root=REPO_ROOT)
    drafts = draft_issues(evidence, limit=args.issues, state=state)

    mode = "create" if args.create_issues else "draft"
    print(f"\n== Issue promotion ({mode}), top {args.issues} pattern families ==")
    if not drafts:
        print("No new pattern families (see .j2py/harvest/state.json filed_signals).")
    else:
        create_issues(drafts, create=args.create_issues, state=state)

    state.last_promotion_at = utc_now_iso()
    save_state(state)
    print(f"\nState: {REPO_ROOT / '.j2py/harvest/state.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
