"""Pydantic Settings scaffolding generation target."""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass
from pathlib import Path

from j2py.wire.schema import WiringSidecar
from j2py.wire.targets.common import GENERATED_HEADER
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
            jdbc_bean = element.spring.get("jdbc_bean")
            if not isinstance(jdbc_bean, dict):
                continue
            bean_name = _str(jdbc_bean.get("name"), default=element.java_name)
            bean_python_name = _str(
                jdbc_bean.get("python_name"),
                default=translate_field_name(element.java_name),
            )
            line = _source_line(jdbc_bean)
            for item in _list_of_dicts(jdbc_bean.get("properties")):
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


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _source_line(value: dict[str, object]) -> int | None:
    location = value.get("source_location")
    if not isinstance(location, dict):
        return None
    line = location.get("line")
    return line if isinstance(line, int) else None


def _str(value: object, *, default: str) -> str:
    return value if isinstance(value, str) else default
