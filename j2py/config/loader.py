"""Layered configuration — inspired by java2python's Config.every()/last() pattern."""

from __future__ import annotations

import difflib
import importlib.util
import os
import sys
import tomllib
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from j2py.config import default

T = TypeVar("T")


class ConfigError(ValueError):
    """Raised when a user config file cannot be parsed or validated."""


class TranslationConfig(BaseModel):
    """Merged, validated configuration for the translation pipeline."""

    model_config = ConfigDict(extra="forbid")

    type_map: dict[str, str] = Field(default_factory=dict)
    collection_map: dict[str, str] = Field(default_factory=dict)
    exception_map: dict[str, str] = Field(default_factory=dict)
    literal_map: dict[str, str] = Field(default_factory=dict)
    import_map: dict[str, str] = Field(default_factory=dict)
    drop_imports: set[str] = Field(default_factory=set)
    drop_annotations: set[str] = Field(default_factory=set)
    strip_modifiers: set[str] = Field(default_factory=set)

    # Behaviour flags
    emit_type_hints: bool = True
    snake_case_methods: bool = True
    snake_case_fields: bool = True
    emit_line_comments: bool = True  # # java: <original line>
    emit_docstrings: bool = True  # Convert Javadoc blocks to Python docstrings
    confidence_comments: bool = True  # # TODO(j2py): low-confidence
    target_python: str = "3.11"
    workers: int = Field(default_factory=lambda: min(8, os.cpu_count() or 1))
    llm_concurrency: int = 4

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

    def add_auto_discovered(self, root: Path) -> ConfigLoader:
        """Load the first conventional project config file found under ``root``."""
        candidates = [
            root / "j2py.yaml",
            root / "j2py.yml",
            root / "j2py.toml",
            root / "pyproject.toml",
            root / "j2py_config.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return self.add_file(candidate)
        return self

    def add_file(self, path: Path) -> ConfigLoader:
        suffix = path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            overrides = _load_yaml(path)
        elif suffix == ".toml":
            overrides = _load_toml(path)
        elif suffix == ".py":
            overrides = _load_python(path)
        else:
            raise ConfigError(f"Unsupported config file extension for {path}")

        self._validate_layer(overrides, path)
        self._layers.append(overrides)
        return self

    def _validate_layer(self, layer: dict[str, Any], path: Path) -> None:
        try:
            TranslationConfig(**layer)
        except ValidationError as exc:
            raise ConfigError(_format_validation_error(path, exc)) from exc

    def build(self) -> TranslationConfig:
        merged: dict[str, Any] = {}
        for layer in self._layers:
            for key, value in layer.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                elif isinstance(value, (set, frozenset, list, tuple)) and isinstance(
                    merged.get(key), (set, frozenset)
                ):
                    merged[key] = merged[key] | set(value)
                else:
                    merged[key] = value
        try:
            return TranslationConfig(**merged)
        except ValidationError as exc:
            raise ConfigError(_format_validation_error(Path("<merged config>"), exc)) from exc


def _load_python(path: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("_j2py_config", path)
    if spec is None or spec.loader is None:
        raise ConfigError(f"Cannot load config from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_j2py_config"] = module
    spec.loader.exec_module(module)

    return {k: v for k, v in vars(module).items() if not k.startswith("_")}


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Error in {path}: {exc}") from exc
    if path.name == "pyproject.toml":
        tool = data.get("tool", {})
        if not isinstance(tool, dict):
            return {}
        j2py = tool.get("j2py", {})
        if not isinstance(j2py, dict):
            raise ConfigError(f"Error in {path}: [tool.j2py] must be a table")
        return _normalize_config_mapping(dict(j2py))
    j2py_section = data.get("j2py")
    if isinstance(j2py_section, dict):
        return _normalize_config_mapping(dict(j2py_section))
    return _normalize_config_mapping(dict(data))


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError(
            f"Error in {path}: YAML config requires PyYAML. "
            "Install with 'pip install j2py-converter[yaml]'."
        ) from exc

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Error in {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Error in {path}: config root must be a mapping")
    return dict(data)


def _normalize_config_mapping(data: dict[str, Any]) -> dict[str, Any]:
    mapping_fields = {
        "type_map",
        "collection_map",
        "exception_map",
        "literal_map",
        "import_map",
    }
    normalized = dict(data)
    for key in mapping_fields:
        value = normalized.get(key)
        if isinstance(value, dict):
            normalized[key] = _flatten_dotted_mapping(value)
    return normalized


def _flatten_dotted_mapping(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            result.update(_flatten_dotted_mapping(value, full_key))
        else:
            result[full_key] = str(value)
    return result


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    messages: list[str] = []
    valid_keys = set(TranslationConfig.model_fields)
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"])
        if error["type"] == "extra_forbidden":
            suggestion = difflib.get_close_matches(loc, valid_keys, n=1)
            hint = f" Did you mean '{suggestion[0]}'?" if suggestion else ""
            messages.append(f"Unknown config key: '{loc}'.{hint}")
        else:
            messages.append(f"{loc}: {error['msg']}")
    joined = "\n  ".join(messages)
    return f"Error in {path}:\n  {joined}"
