from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def versions_module():
    path = Path(__file__).resolve().parents[2] / "scripts/packaging/check_release_versions.py"
    spec = importlib.util.spec_from_file_location("check_release_versions", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_release_versions_match(versions_module) -> None:
    assert versions_module.check_release_versions() is None


def test_release_versions_detects_mismatch(tmp_path: Path, versions_module) -> None:
    (tmp_path / "j2py").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "j2py-converter"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    (tmp_path / "j2py" / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")

    error = versions_module.check_release_versions(tmp_path)
    assert error is not None
    assert "1.2.3" in error
    assert "9.9.9" in error
