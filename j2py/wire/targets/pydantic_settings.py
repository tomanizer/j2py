"""Pydantic Settings scaffolding generation target."""

from __future__ import annotations

import ast
import keyword
import re
from dataclasses import dataclass
from pathlib import Path

from j2py.wire.schema import WiringSidecar
from j2py.wire.targets.common import GENERATED_HEADER, as_str, list_of_dicts
from j2py.wiring_contract import translate_field_name

SETTINGS_FILENAME = "settings.py"

_NON_IDENTIFIER_CHARS_RE = re.compile(r"[^0-9A-Za-z_]+")
_UNDERSCORE_RE = re.compile(r"_+")


@dataclass(frozen=True)
class SettingsPropertySpec:
    """One visible source configuration property recorded in sidecar metadata."""

    source: str
    bean_name: str
    bean_python_name: str
    target: str
    key: str
    field_name: str
    line: int | None


class PydanticSettingsTarget:
    """Generate Pydantic Settings scaffolding from Spring property metadata."""

    def __init__(self, *, translated_root: Path) -> None:
        self.translated_root = translated_root

    def generate(self, sidecars: list[WiringSidecar], output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / SETTINGS_FILENAME
        path.write_text(render_settings(settings_property_specs(sidecars)), encoding="utf-8")
        return [path]


def settings_property_specs(sidecars: list[WiringSidecar]) -> list[SettingsPropertySpec]:
    """Return visible Spring property keys recorded in wiring sidecars."""
    specs: list[SettingsPropertySpec] = []
    for sidecar in sidecars:
        for element in sidecar.elements:
            spring = element.spring
            if not isinstance(spring, dict):
                continue
            jdbc_bean = spring.get("jdbc_bean")
            if not isinstance(jdbc_bean, dict):
                continue
            bean_name = as_str(jdbc_bean.get("name"), default=element.java_name)
            bean_python_name = as_str(
                jdbc_bean.get("python_name"),
                default=translate_field_name(element.java_name),
            )
            line = _source_line(jdbc_bean)
            for item in list_of_dicts(jdbc_bean.get("properties")):
                target = item.get("target")
                key = item.get("key")
                if not isinstance(target, str) or not isinstance(key, str) or not key:
                    continue
                specs.append(
                    SettingsPropertySpec(
                        source=sidecar.source,
                        bean_name=bean_name,
                        bean_python_name=bean_python_name,
                        target=target,
                        key=key,
                        field_name=field_name_for_property_key(key),
                        line=line,
                    ),
                )
    return sorted(
        specs,
        key=lambda spec: (spec.field_name, spec.key, spec.bean_python_name, spec.target),
    )


def has_pydantic_settings_facts(sidecars: list[WiringSidecar]) -> bool:
    """Return whether sidecars contain facts consumed by the Pydantic Settings target."""
    return bool(settings_property_specs(sidecars))


def duplicate_property_keys(
    sidecars: list[WiringSidecar],
) -> dict[str, list[SettingsPropertySpec]]:
    """Return source property keys recorded more than once."""
    by_key: dict[str, list[SettingsPropertySpec]] = {}
    for spec in settings_property_specs(sidecars):
        by_key.setdefault(spec.key, []).append(spec)
    return {key: specs for key, specs in by_key.items() if len(specs) > 1}


def field_name_collisions(
    sidecars: list[WiringSidecar],
) -> dict[str, list[SettingsPropertySpec]]:
    """Return normalized settings field names that map distinct source keys."""
    by_field: dict[str, list[SettingsPropertySpec]] = {}
    for spec in settings_property_specs(sidecars):
        by_field.setdefault(spec.field_name, []).append(spec)
    return {
        field_name: specs
        for field_name, specs in by_field.items()
        if len({spec.key for spec in specs}) > 1
    }


def missing_settings_property_bindings(
    sidecars: list[WiringSidecar],
    settings_source: str,
) -> list[SettingsPropertySpec]:
    """Return settings properties not represented in generated settings source."""
    bindings = _settings_bindings(settings_source)
    expected = _unique_specs_by_key(settings_property_specs(sidecars))
    missing: list[SettingsPropertySpec] = []
    for spec in expected:
        binding = bindings.get(spec.field_name)
        if binding is None:
            missing.append(spec)
            continue
        if binding.source_key != spec.key or binding.validation_alias != spec.key:
            missing.append(spec)
    return missing


def render_settings(specs: list[SettingsPropertySpec]) -> str:
    """Render a deterministic Pydantic Settings scaffold."""
    unique_specs = _unique_specs_by_key(specs)
    lines = [
        GENERATED_HEADER,
        "from __future__ import annotations",
        "",
        "from pydantic import Field",
        "from pydantic_settings import BaseSettings, SettingsConfigDict",
        "",
        "# TODO(j2py): decide project environment variable names, defaults, secrets",
        "# source, and deployment config policy before using this in production.",
        "# Currently this uses visible JDBC datasource properties only; @Value and",
        "# @ConfigurationProperties need additional sidecar metadata to appear here.",
        f"SOURCE_PROPERTY_KEYS: dict[str, str] = {_source_property_keys_literal(unique_specs)}",
        "",
        "",
        "class ApplicationSettings(BaseSettings):",
        '    """Settings scaffold extracted from visible Spring property metadata."""',
        "",
        '    model_config = SettingsConfigDict(extra="ignore")',
    ]
    if unique_specs:
        for spec in unique_specs:
            lines.extend(
                [
                    "",
                    f"    # Spring property: {spec.key}",
                    f"    # Source: {spec.source}::{spec.bean_name}.{spec.target}",
                    (
                        f"    {spec.field_name}: str | None = Field("
                        f"default=None, validation_alias={spec.key!r})"
                    ),
                ],
            )
    else:
        lines.extend(
            [
                "",
                "    # TODO(j2py): no visible Spring property keys were found in sidecars.",
                "    pass",
            ],
        )
    lines.extend(
        [
            "",
            "",
            "# Move construction to an application entry point if required settings",
            "# should fail during startup validation instead of module import.",
            "settings = ApplicationSettings()",
        ],
    )
    return "\n".join(lines).rstrip() + "\n"


def field_name_for_property_key(key: str) -> str:
    """Return a stable Python field name for a Spring property key."""
    cleaned = _NON_IDENTIFIER_CHARS_RE.sub("_", key.strip())
    cleaned = _UNDERSCORE_RE.sub("_", cleaned).strip("_").lower()
    if not cleaned:
        cleaned = "setting"
    if cleaned[0].isdigit():
        cleaned = f"setting_{cleaned}"
    if keyword.iskeyword(cleaned):
        cleaned = f"{cleaned}_"
    return cleaned


def _unique_specs_by_key(specs: list[SettingsPropertySpec]) -> list[SettingsPropertySpec]:
    by_key: dict[str, SettingsPropertySpec] = {}
    for spec in specs:
        by_key.setdefault(spec.key, spec)
    return sorted(by_key.values(), key=lambda spec: (spec.field_name, spec.key))


def _source_property_keys_literal(specs: list[SettingsPropertySpec]) -> str:
    if not specs:
        return "{}"
    mapping = {spec.field_name: spec.key for spec in specs}
    return repr(dict(sorted(mapping.items())))


@dataclass(frozen=True)
class _SettingsBinding:
    source_key: str | None
    validation_alias: str | None


def _settings_bindings(source: str) -> dict[str, _SettingsBinding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    source_keys = _source_property_keys(tree)
    aliases = _settings_validation_aliases(tree)
    return {
        field_name: _SettingsBinding(
            source_key=source_keys.get(field_name),
            validation_alias=aliases.get(field_name),
        )
        for field_name in set(source_keys) | set(aliases)
    }


def _source_property_keys(tree: ast.Module) -> dict[str, str]:
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "SOURCE_PROPERTY_KEYS":
                value = node.value
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SOURCE_PROPERTY_KEYS"
            for target in node.targets
        ):
            value = node.value
        if isinstance(value, ast.Dict):
            return _literal_str_dict(value)
    return {}


def _settings_validation_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "ApplicationSettings":
            continue
        for item in node.body:
            if (
                not isinstance(item, ast.AnnAssign)
                or not isinstance(item.target, ast.Name)
                or not isinstance(item.value, ast.Call)
            ):
                continue
            alias = _field_validation_alias(item.value)
            if alias is not None:
                aliases[item.target.id] = alias
        return aliases
    return aliases


def _field_validation_alias(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        if call.func.id != "Field":
            return None
    elif isinstance(call.func, ast.Attribute):
        if call.func.attr != "Field":
            return None
    else:
        return None
    for keyword_arg in call.keywords:
        if keyword_arg.arg != "validation_alias":
            continue
        if isinstance(keyword_arg.value, ast.Constant) and isinstance(
            keyword_arg.value.value,
            str,
        ):
            return keyword_arg.value.value
    return None


def _literal_str_dict(node: ast.Dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for key_node, value_node in zip(node.keys, node.values, strict=True):
        if (
            isinstance(key_node, ast.Constant)
            and isinstance(key_node.value, str)
            and isinstance(value_node, ast.Constant)
            and isinstance(value_node.value, str)
        ):
            values[key_node.value] = value_node.value
    return values


def _source_line(value: dict[str, object]) -> int | None:
    location = value.get("source_location")
    if not isinstance(location, dict):
        return None
    line = location.get("line")
    return line if isinstance(line, int) else None
