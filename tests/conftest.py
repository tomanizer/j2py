"""Shared pytest fixtures for the j2py test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from j2py.config.loader import ConfigLoader, TranslationConfig

FIXTURES = Path(__file__).parent / "fixtures"
JAVA_FIXTURES = FIXTURES / "java"
PYTHON_FIXTURES = FIXTURES / "python"
TARGET_FIXTURES = JAVA_FIXTURES / "targets"
CORPUS_CONSTRUCT_FIXTURES = FIXTURES / "corpus" / "constructs"


@pytest.fixture(scope="session")
def cfg() -> TranslationConfig:
    return ConfigLoader().add_defaults().build()
