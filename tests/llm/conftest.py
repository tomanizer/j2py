"""Bootstrap ANTHROPIC_API_KEY for live LLM tests.

Cursor/VS Code terminals and ``make`` often run without sourcing ``~/.zshrc``.
When the key is still missing after loading the repo ``.env``, try the user's
interactive zsh login shell.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from j2py.dotenv import load_repo_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_from_zsh_login() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        key = subprocess.check_output(
            ["zsh", "-lic", "print -r -- ${ANTHROPIC_API_KEY}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key


load_repo_dotenv(repo_root=_REPO_ROOT)
_load_from_zsh_login()
