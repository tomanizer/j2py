from __future__ import annotations

import importlib
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

SPRING_RUNTIME_DEPENDENCIES = {
    "fastapi",
    "httpx",
    "pydantic-settings",
    "sqlalchemy",
}
SPRING_RUNTIME_IMPORTS = {
    "fastapi",
    "httpx",
    "pydantic_settings",
    "sqlalchemy",
}


def _pyproject() -> dict[str, object]:
    path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _dependency_names(dependencies: list[str]) -> set[str]:
    return {dependency.split(">=", 1)[0].lower() for dependency in dependencies}


def test_optional_provider_sdks_are_not_default_dependencies() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)

    dependencies = project["dependencies"]
    assert isinstance(dependencies, list)

    assert "google-genai" not in _dependency_names(dependencies)
    assert "openai" not in _dependency_names(dependencies)


def test_google_genai_is_available_in_gemini_and_dev_extras() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    optional = project["optional-dependencies"]
    assert isinstance(optional, dict)

    gemini = optional["gemini"]
    dev = optional["dev"]
    assert isinstance(gemini, list)
    assert isinstance(dev, list)

    assert "google-genai" in _dependency_names(gemini)
    assert "google-genai" in _dependency_names(dev)


def test_openai_sdk_is_available_in_openai_and_dev_extras() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    optional = project["optional-dependencies"]
    assert isinstance(optional, dict)

    openai = optional["openai"]
    dev = optional["dev"]
    assert isinstance(openai, list)
    assert isinstance(dev, list)

    assert "openai" in _dependency_names(openai)
    assert "openai" in _dependency_names(dev)


def test_spring_runtime_dependencies_are_available_in_spring_extra_only() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    dependencies = project["dependencies"]
    optional = project["optional-dependencies"]
    assert isinstance(dependencies, list)
    assert isinstance(optional, dict)

    spring = optional["spring"]
    assert isinstance(spring, list)

    default_names = _dependency_names(dependencies)
    spring_names = _dependency_names(spring)

    assert SPRING_RUNTIME_DEPENDENCIES.isdisjoint(default_names)
    assert spring_names >= SPRING_RUNTIME_DEPENDENCIES


def test_default_imports_do_not_require_spring_extra_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    code = """
from __future__ import annotations

import importlib.abc
import sys


class BlockSpringExtra(importlib.abc.MetaPathFinder):
    blocked = {"fastapi", "httpx", "pydantic_settings", "sqlalchemy", "starlette"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in self.blocked:
            raise ImportError(f"blocked optional Spring dependency: {fullname}")
        return None


sys.meta_path.insert(0, BlockSpringExtra())

import j2py
import j2py.cli.main
import j2py.config.loader
import j2py.translate.skeleton
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_spring_extra_runtime_imports_when_installed() -> None:
    missing = [
        module_name
        for module_name in sorted(SPRING_RUNTIME_IMPORTS)
        if importlib.util.find_spec(module_name) is None
    ]
    if missing:
        pytest.skip(
            "Install the Spring extra to run this import smoke test: "
            "uv run --extra spring --extra test pytest "
            "tests/packaging/test_pyproject_dependencies.py -k spring_extra_runtime",
        )

    for module_name in sorted(SPRING_RUNTIME_IMPORTS):
        importlib.import_module(module_name)


def test_gemini_harvest_make_targets_request_gemini_extra() -> None:
    path = Path(__file__).resolve().parents[2] / "Makefile"
    makefile = path.read_text(encoding="utf-8")

    assert "uv run --extra gemini python scripts/harvest/run_llm_harvest.py" in makefile
    assert "uv run --extra gemini python scripts/harvest/run_harvest_promotion.py" in makefile
