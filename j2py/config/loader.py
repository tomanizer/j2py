"""Layered configuration — inspired by java2python's Config.every()/last() pattern."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from j2py.config import default

T = TypeVar("T")


class TranslationConfig(BaseModel):
    """Merged, validated configuration for the translation pipeline."""

    type_map: dict[str, str] = {}
    collection_map: dict[str, str] = {}
    exception_map: dict[str, str] = {}
    literal_map: dict[str, str] = {}
    import_map: dict[str, str] = {}
    drop_imports: set[str] = set()
    drop_annotations: set[str] = set()
    strip_modifiers: set[str] = set()

    # Behaviour flags
    emit_type_hints: bool = True
    snake_case_methods: bool = True
    snake_case_fields: bool = True
    emit_line_comments: bool = True    # # java: <original line>
    emit_docstrings: bool = True       # Convert Javadoc blocks to Python docstrings
    confidence_comments: bool = True   # # TODO(j2py): low-confidence
    target_python: str = "3.11"

    @classmethod
    def default(cls) -> TranslationConfig:
        return cls(
            type_map=dict(default.TYPE_MAP),
            collection_map=dict(default.COLLECTION_MAP),
            exception_map=dict(default.EXCEPTION_MAP),
            literal_map=dict(default.LITERAL_MAP),
            import_map=dict(default.IMPORT_MAP),
            drop_imports=set(default.DROP_IMPORTS),
            drop_annotations=set(default.DROP_ANNOTATIONS),
            strip_modifiers=set(default.STRIP_MODIFIERS),
        )


class ConfigLoader:
    """Loads and merges multiple config layers (last wins for scalar keys,
    dicts are merged with later layers overriding earlier ones)."""

    def __init__(self) -> None:
        self._layers: list[dict[str, Any]] = []

    def add_defaults(self) -> ConfigLoader:
        self._layers.append(TranslationConfig.default().model_dump())
        return self

    def add_file(self, path: Path) -> ConfigLoader:
        spec = importlib.util.spec_from_file_location("_j2py_config", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load config from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["_j2py_config"] = module
        spec.loader.exec_module(module)

        overrides: dict[str, Any] = {
            k: v for k, v in vars(module).items() if not k.startswith("_")
        }
        self._layers.append(overrides)
        return self

    def build(self) -> TranslationConfig:
        merged: dict[str, Any] = {}
        for layer in self._layers:
            for key, value in layer.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                elif isinstance(value, (set, frozenset)) and isinstance(
                    merged.get(key), (set, frozenset)
                ):
                    merged[key] = merged[key] | set(value)
                else:
                    merged[key] = value
        return TranslationConfig(**merged)
