"""Load a repo-root ``.env`` file into ``os.environ`` (without extra dependencies)."""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()
    key, _, value = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return key, value


def _dotenv_candidates(repo_root: Path) -> list[Path]:
    """Return ``.env`` paths to try, in precedence order (first wins per key)."""
    candidates = [repo_root / ".env"]
    corpus_root = os.environ.get("J2PY_CORPUS_ROOT", "").strip()
    if corpus_root:
        shared = Path(corpus_root) / ".env"
        if shared not in candidates:
            candidates.append(shared)
    return candidates


def _load_env_file(env_path: Path) -> None:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if value:
            os.environ.setdefault(key, value)


def load_repo_dotenv(*, repo_root: Path | None = None) -> None:
    """Populate unset environment variables from ``<repo>/.env``.

    In git worktrees, also loads ``$J2PY_CORPUS_ROOT/.env`` when the checkout
    has no local ``.env`` (same pattern as shared ``.corpus/`` checkouts).
    """
    global _LOADED
    if _LOADED:
        return
    _LOADED = True

    root = repo_root or _repo_root()
    for env_path in _dotenv_candidates(root):
        if env_path.is_file():
            _load_env_file(env_path)
