from __future__ import annotations

import tomllib
from pathlib import Path


def _pyproject() -> dict[str, object]:
    path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _dependency_names(dependencies: list[str]) -> set[str]:
    return {dependency.split(">=", 1)[0].lower() for dependency in dependencies}


def test_google_genai_is_not_a_default_dependency() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)

    dependencies = project["dependencies"]
    assert isinstance(dependencies, list)

    assert "google-genai" not in _dependency_names(dependencies)


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
