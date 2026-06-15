#!/usr/bin/env python3
"""Run translate_file(use_llm=True) over a harvest preset or file list and append records."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from tenacity import RetryError

from j2py.config.loader import ConfigLoader
from j2py.dotenv import load_repo_dotenv
from j2py.llm.client import LLMProvider, resolve_model
from j2py.llm.harvest import harvest_records_path, llm_harvest_enabled
from j2py.llm.usage import (
    begin_usage_session,
    format_usage_summary,
    session_record_count,
    session_records_slice,
    session_usage_totals,
    summarize_usage_records,
    usage_log_path,
)
from j2py.pipeline import translate_file
from scripts.harvest.harvest_presets import DEFAULT_HARVEST_PRESET, HARVEST_PRESETS

TEMP_PATH_MARKERS = ("/pytest-", "/tmp/pytest", "/var/folders/")


def is_temp_harvest_path(path: Path) -> bool:
    """Return True for pytest temp dirs and other paths that pollute triage."""
    text = path.as_posix()
    return any(marker in text for marker in TEMP_PATH_MARKERS)


def is_package_info_path(path: Path) -> bool:
    """Return True for Java package descriptor files (no real class body to harvest)."""
    return path.name == "package-info.java"


def should_skip_harvest_path(
    path: Path,
    *,
    skip_temp_paths: bool,
    skip_package_info: bool,
) -> bool:
    if skip_temp_paths and is_temp_harvest_path(path):
        return True
    return skip_package_info and is_package_info_path(path)


def load_paths_from_file(file_list: Path) -> list[Path]:
    """Load Java paths from a newline-separated queue file."""
    if not file_list.is_file():
        raise FileNotFoundError(f"Queue file not found: {file_list}")
    paths: list[Path] = []
    for line in file_list.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        paths.append(Path(stripped))
    return paths


def select_paths(
    paths: list[Path],
    *,
    offset: int,
    limit: int,
    skip_temp_paths: bool,
    skip_package_info: bool,
) -> list[Path]:
    """Apply offset/limit and optional low-signal path filtering."""
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit < 0:
        raise ValueError("limit must be >= 0")

    filtered = [
        path
        for path in paths
        if not should_skip_harvest_path(
            path,
            skip_temp_paths=skip_temp_paths,
            skip_package_info=skip_package_info,
        )
    ]
    sliced = filtered[offset:]
    if limit > 0:
        sliced = sliced[:limit]
    return sliced


def require_api_key(provider: LLMProvider) -> None:
    load_repo_dotenv()
    env_var = "GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
    if os.environ.get(env_var):
        return
    print(f"ERROR: {env_var} is not set.", file=sys.stderr)
    print("  Use .env, export in shell, or source ~/.zshrc", file=sys.stderr)
    raise SystemExit(2)


def resolve_harvest_paths(
    *,
    preset: str,
    file_list: Path | None,
    offset: int,
    limit: int,
    skip_temp_paths: bool,
    skip_package_info: bool,
) -> tuple[list[Path], str]:
    """Return paths to translate and a short label for logging."""
    if file_list is not None:
        paths = load_paths_from_file(file_list)
        label = f"file-list={file_list}"
    else:
        paths = list(HARVEST_PRESETS[preset])
        label = f"preset={preset}"

    selected = select_paths(
        paths,
        offset=offset,
        limit=limit,
        skip_temp_paths=skip_temp_paths,
        skip_package_info=skip_package_info,
    )
    return selected, label


def is_gemini_quota_error(exc: BaseException) -> bool:
    """Return True when the Gemini API rejected the call for rate/daily quota."""
    current: BaseException | None = exc
    while current is not None:
        status_code = getattr(current, "status_code", None)
        if status_code == 429:
            return True
        text = str(current)
        if "RESOURCE_EXHAUSTED" in text or ("429" in text and "quota" in text.lower()):
            return True
        current = current.__cause__ or current.__context__
    return False


def format_gemini_quota_message(exc: BaseException) -> str:
    text = str(exc)
    if "Please retry in" in text:
        return text.split("Please retry in", 1)[0].strip()
    return "Gemini API quota exceeded (429 RESOURCE_EXHAUSTED)."


def run_harvest(
    paths: list[Path],
    *,
    provider: LLMProvider,
    model: str | None,
    validate: bool,
    sleep_seconds: float,
) -> tuple[int, int]:
    """Translate paths and return (used_llm_count, skipped_count)."""
    cfg = ConfigLoader().add_defaults().build()
    used_llm = 0
    skipped = 0
    resolved_model = resolve_model(provider, model)
    begin_usage_session()

    for index, path in enumerate(paths):
        if not path.is_file():
            print(f"ERROR: missing file: {path}", file=sys.stderr)
            raise SystemExit(2)

        usage_start = session_record_count()
        try:
            result = translate_file(
                path,
                cfg=cfg,
                use_llm=True,
                model=resolved_model,
                llm_provider=provider,
                validate=validate,
            )
        except RetryError as exc:
            cause = exc.last_attempt.exception() if exc.last_attempt else exc
            if provider == "gemini" and cause is not None and is_gemini_quota_error(cause):
                processed = used_llm + skipped
                resume_offset_hint = processed
                print(
                    f"\nGemini quota hit after {processed} file(s) in this batch.",
                    file=sys.stderr,
                )
                print(format_gemini_quota_message(cause), file=sys.stderr)
                print(
                    "Free tier for gemini-3.5-flash is often ~20 requests/day per project. "
                    "Each file can use 1–3 calls (initial + mypy repair retries).",
                    file=sys.stderr,
                )
                print(
                    f"Resume with: make harvest-gemini OFFSET={resume_offset_hint} LIMIT=10 "
                    "(use LIMIT=2 on free tier)",
                    file=sys.stderr,
                )
                print("Monitor usage: https://ai.dev/rate-limit", file=sys.stderr)
                print(format_usage_summary(session_usage_totals(), prefix="partial"))
                print(f"Usage log: {usage_log_path()}")
                raise SystemExit(3) from exc
            raise

        if result.used_llm:
            used_llm += 1
            file_usage = summarize_usage_records(session_records_slice(usage_start))
            print(
                f"  LLM  {path.name} confidence={result.confidence:.2f} "
                f"{format_usage_summary(file_usage)}"
            )
            if sleep_seconds > 0 and index < len(paths) - 1:
                time.sleep(sleep_seconds)
        else:
            skipped += 1
            print(f"  skip {path.name} (rule layer complete)")

    return used_llm, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=sorted(HARVEST_PRESETS),
        default=DEFAULT_HARVEST_PRESET,
        help=f"File set when --file-list is omitted (default: {DEFAULT_HARVEST_PRESET})",
    )
    parser.add_argument(
        "--file-list",
        type=Path,
        default=None,
        help="Newline-separated Java paths (from corpus scan queue); overrides --preset",
    )
    parser.add_argument(
        "--llm-provider",
        choices=("anthropic", "gemini"),
        default="gemini",
        help="LLM provider (default: gemini for batch harvest)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model ID (default: provider-specific)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N paths after filtering (for resume)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max files to translate (0 = all remaining after --offset)",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=6.0,
        help="Delay after each LLM call (~10 RPM at 6s; 0 = no throttle)",
    )
    parser.add_argument(
        "--skip-temp-paths",
        action="store_true",
        help="Drop pytest/temp paths (recommended for corpus queues)",
    )
    parser.add_argument(
        "--skip-package-info",
        action="store_true",
        help="Drop package-info.java files (package descriptors, not real classes)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip post-translation validation (faster, less signal in records)",
    )
    args = parser.parse_args()

    if not llm_harvest_enabled():
        print("ERROR: J2PY_LLM_HARVEST=0 — recording disabled.", file=sys.stderr)
        return 2

    provider: LLMProvider = args.llm_provider
    require_api_key(provider)

    try:
        paths, label = resolve_harvest_paths(
            preset=args.preset,
            file_list=args.file_list,
            offset=args.offset,
            limit=args.limit,
            skip_temp_paths=args.skip_temp_paths,
            skip_package_info=args.skip_package_info,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not paths:
        print("No files to translate (empty queue or offset past end).")
        return 0

    print(
        f"Harvest run {label} provider={provider} "
        f"model={resolve_model(provider, args.model)} files={len(paths)}",
    )
    used_llm, skipped = run_harvest(
        paths,
        provider=provider,
        model=args.model,
        validate=not args.no_validate,
        sleep_seconds=args.sleep_seconds,
    )

    out = harvest_records_path()
    print(f"\nDone: llm={used_llm} skipped={skipped}")
    print(format_usage_summary(session_usage_totals()))
    print(f"Records: {out}")
    print(f"Usage log: {usage_log_path()}")
    print("Next: make harvest-triage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
