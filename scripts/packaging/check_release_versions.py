"""Fail when pyproject.toml and j2py.__version__ disagree."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def pyproject_version(root: Path = ROOT) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def init_version(root: Path = ROOT) -> str:
    text = (root / "j2py" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if match is None:
        msg = "j2py/__init__.py: __version__ assignment not found"
        raise ValueError(msg)
    return match.group(1)


def check_release_versions(root: Path = ROOT) -> str | None:
    expected = pyproject_version(root)
    actual = init_version(root)
    if expected != actual:
        return (
            f"Version mismatch: pyproject.toml has {expected!r}, "
            f"j2py/__init__.py has {actual!r}"
        )
    return None


def main() -> int:
    error = check_release_versions()
    if error is not None:
        print(error, file=sys.stderr)
        return 1
    print(f"Release versions match: {pyproject_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
