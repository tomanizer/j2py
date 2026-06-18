"""Registry and writer for generated behavior-equivalence fixtures."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

CASES: dict[str, str] = {}
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "behavior"


def case(name: str, src: str) -> None:
    CASES[name] = src.lstrip()


def write_cases(out: Path, cases: dict[str, str] = CASES) -> None:
    out.mkdir(parents=True, exist_ok=True)
    # Only (re)write the directories this generator owns; hand-written fixtures and
    # other cases in the same directory are left untouched.
    for name, src in cases.items():
        d = out / name
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        (d / "Main.java").write_text(src, encoding="utf-8")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    write_cases(out)
    print(f"generated {len(CASES)} cases into {out}")
