"""Tests for repo-root .env loading."""

from __future__ import annotations

import os

from j2py import dotenv


def test_load_repo_dotenv_populates_unset_variables(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("J2PY_DOTENV_PROBE", raising=False)
    dotenv._LOADED = False
    (tmp_path / ".env").write_text(
        "J2PY_DOTENV_PROBE=from-file\nEXISTING=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "from-shell")

    dotenv.load_repo_dotenv(repo_root=tmp_path)

    assert os.environ["J2PY_DOTENV_PROBE"] == "from-file"
    assert os.environ["EXISTING"] == "from-shell"
    dotenv._LOADED = False
