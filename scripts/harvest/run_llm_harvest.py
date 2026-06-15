#!/usr/bin/env python3
"""Run translate_file(use_llm=True) over a harvest preset and append records."""

from __future__ import annotations

import argparse
import os
import sys

from j2py.config.loader import ConfigLoader
from j2py.dotenv import load_repo_dotenv
from j2py.llm.client import DEFAULT_MODELS, LLMProvider
from j2py.llm.harvest import harvest_records_path, llm_harvest_enabled
from j2py.pipeline import translate_file
from scripts.harvest.harvest_presets import DEFAULT_HARVEST_PRESET, HARVEST_PRESETS


def _require_api_key(provider: LLMProvider) -> None:
    load_repo_dotenv()
    env_var = "GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
    if os.environ.get(env_var):
        return
    print(f"ERROR: {env_var} is not set.", file=sys.stderr)
    print("  Use .env, export in shell, or source ~/.zshrc", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=sorted(HARVEST_PRESETS),
        default=DEFAULT_HARVEST_PRESET,
        help=f"File set to translate (default: {DEFAULT_HARVEST_PRESET})",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model for LLM completion (default depends on --llm-provider)",
    )
    parser.add_argument(
        "--llm-provider",
        choices=("anthropic", "gemini"),
        default="anthropic",
        help="LLM provider for completion",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max files to translate (0 = all in preset)",
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

    provider = args.llm_provider
    model = args.model or DEFAULT_MODELS[provider]

    _require_api_key(provider)

    paths = list(HARVEST_PRESETS[args.preset])
    if args.limit > 0:
        paths = paths[: args.limit]

    missing = [path for path in paths if not path.is_file()]
    if missing:
        for path in missing:
            print(f"ERROR: missing probe file: {path}", file=sys.stderr)
        return 2

    cfg = ConfigLoader().add_defaults().build()
    used_llm = 0
    skipped = 0

    print(f"Harvest run preset={args.preset} files={len(paths)}")
    for path in paths:
        result = translate_file(
            path,
            cfg=cfg,
            use_llm=True,
            model=model,
            llm_provider=provider,
            validate=not args.no_validate,
        )
        if result.used_llm:
            used_llm += 1
            print(f"  LLM  {path.name} confidence={result.confidence:.2f}")
        else:
            skipped += 1
            print(f"  skip {path.name} (rule layer complete)")

    out = harvest_records_path()
    print(f"\nDone: llm={used_llm} skipped={skipped}")
    print(f"Records: {out}")
    print("Next: make harvest-triage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
