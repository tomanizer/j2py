"""Fail when source distributions contain local/generated project state."""

from __future__ import annotations

import re
import sys
import tarfile
from pathlib import Path

FORBIDDEN_ENTRY_RE = re.compile(
    r"^[^/]+/"
    r"("
    r"\.claude(?:/|$)|"
    r"\.codex(?:/|$)|"
    r"\.claire(?:/|$)|"
    r"\.venv(?:/|$)|"
    r"\.corpus(?:/|$)|"
    r"corpus-reports(?:/|$)|"
    r"dist(?:/|$)|"
    r"\.mypy_cache[^/]*(?:/|$)|"
    r"\.pytest_cache[^/]*(?:/|$)|"
    r"\.ruff_cache[^/]*(?:/|$)|"
    r"(?:.*/)?__pycache__[^/]*(?:/|$)|"
    r".*\.(?:pyc|pyo)$|"
    r"packages/j2py-vscode/node_modules(?:/|$)|"
    r"packages/j2py-vscode/out(?:/|$)|"
    r"packages/j2py-vscode/.*\.vsix$"
    r")"
)


def forbidden_entries(path: Path) -> list[str]:
    with tarfile.open(path, "r:gz") as archive:
        return [name for name in archive.getnames() if FORBIDDEN_ENTRY_RE.search(name)]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_sdist_hygiene.py dist/*.tar.gz", file=sys.stderr)
        return 2

    failed = False
    for raw_path in argv[1:]:
        path = Path(raw_path)
        try:
            matches = forbidden_entries(path)
        except FileNotFoundError:
            print(f"Error: File '{path}' not found.", file=sys.stderr)
            failed = True
            continue
        except tarfile.TarError as exc:
            print(f"Error: Failed to read tar archive '{path}': {exc}", file=sys.stderr)
            failed = True
            continue

        if not matches:
            print(f"{path}: clean")
            continue
        failed = True
        print(f"{path}: forbidden source distribution entries:", file=sys.stderr)
        for entry in matches[:50]:
            print(f"  {entry}", file=sys.stderr)
        if len(matches) > 50:
            print(f"  ... {len(matches) - 50} more", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
