"""Shared environment parsing helpers for LLM features."""

from __future__ import annotations

import os

_FALSE_ENV_VALUES = {"0", "false", "no", "off"}


def enabled_env_flag(name: str, *, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in _FALSE_ENV_VALUES
