"""Framework-neutral provider generation target."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from j2py.wire.schema import WiringElement, WiringSidecar
from j2py.wire.targets.common import (
    GENERATED_HEADER,
    base_type,
    constructor_parameters,
    injection_specs,
    provider_identity,
    should_import_type,
    type_modules,
)
from j2py.wiring_contract import translate_field_name

PROVIDERS_FILENAME = "providers.py"
_PROVIDER_ROLES = {"component", "controller", "repository", "service"}


@dataclass(frozen=True)
class ProviderInjectionSpec:
    name: str
    python_type: str


@dataclass(frozen=True)
class ProviderSpec:
    identity: str
    provider_name: str
    class_name: str
    module: str
    role: str
    injections: list[ProviderInjectionSpec]


class ProvidersTarget:
    """Generate plain Python factory functions from Spring wiring sidecars."""

    def __init__(self, *, translated_root: Path) -> None:
        self.translated_root = translated_root

    def generate(self, sidecars: list[WiringSidecar], output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / PROVIDERS_FILENAME
        specs = provider_specs(sidecars, self.translated_root)
        path.write_text(
            render_providers(specs, type_modules(sidecars, self.translated_root)),
            encoding="utf-8",
        )
        return [path]


def provider_specs(sidecars: list[WiringSidecar], translated_root: Path) -> list[ProviderSpec]:
    """Return provider specs derived from class roles and local injection metadata."""
    specs: list[ProviderSpec] = []
    for sidecar in sidecars:
        module = sidecar.python_module(translated_root)
        for index, element in enumerate(sidecar.elements):
            if element.kind != "class":
                continue
            role = _str(element.spring.get("role"), default="")
            if role not in _PROVIDER_ROLES:
                continue
            identity = provider_identity(element)
            sidecar_injections = _injections_for_class(sidecar.elements, index)
            constructor_params = _constructor_parameters(Path(sidecar.output), element.python_name)
            specs.append(
                ProviderSpec(
                    identity=identity,
                    provider_name=f"get_{translate_field_name(identity)}",
                    class_name=element.python_name,
                    module=module,
                    role=role,
                    injections=_merge_injections(constructor_params, sidecar_injections),
                ),
            )
    return _ordered_specs(specs)


def expected_provider_names(sidecars: list[WiringSidecar], translated_root: Path) -> set[str]:
    """Return generated provider function names for validation checks."""
    return {spec.provider_name for spec in provider_specs(sidecars, translated_root)}


def provider_name_collisions(
    sidecars: list[WiringSidecar],
    translated_root: Path,
) -> dict[str, list[ProviderSpec]]:
    """Return provider functions that would be emitted for multiple identities."""
    return provider_name_collisions_from_specs(provider_specs(sidecars, translated_root))


def provider_cycles(sidecars: list[WiringSidecar], translated_root: Path) -> list[list[str]]:
    """Return provider dependency cycles by provider function name."""
    specs = provider_specs(sidecars, translated_root)
    dependencies = _provider_dependencies(specs)
    pending = set(dependencies)
    ordered: set[str] = set()
    while pending:
        ready = {name for name in pending if all(dep in ordered for dep in dependencies[name])}
        if not ready:
            return [sorted(pending)]
        ordered.update(ready)
        pending.difference_update(ready)
    return []


def missing_injection_provider_edges(
    sidecars: list[WiringSidecar],
    translated_root: Path,
) -> list[tuple[WiringSidecar, WiringElement, str]]:
    """Return injection edges that cannot be satisfied by another generated provider."""
    specs = provider_specs(sidecars, translated_root)
    identities = {_normalize_identity(spec.identity) for spec in specs}
    missing: list[tuple[WiringSidecar, WiringElement, str]] = []
    for sidecar in sidecars:
        for element in sidecar.elements:
            inject = element.spring.get("inject")
            if not isinstance(inject, dict):
                continue
            name = inject.get("name")
            if not isinstance(name, str) or not name:
                continue
            if _normalize_identity(name) not in identities:
                missing.append((sidecar, element, name))
    return missing


def render_providers(
    specs: list[ProviderSpec],
    type_modules: dict[str, str] | None = None,
) -> str:
    """Render importable provider module source."""
    imports = _imports_for_specs(specs, type_modules)
    lines = [
        GENERATED_HEADER,
        "from __future__ import annotations",
        "",
    ]
    for module in sorted(imports):
        names = ", ".join(sorted(imports[module]))
        lines.append(f"from {module} import {names}")
    if imports:
        lines.append("")
    for index, spec in enumerate(specs):
        if index:
            lines.extend(["", ""])
        lines.extend(_render_provider(spec))
    if not specs:
        lines.append("__all__: list[str] = []")
    return "\n".join(lines).rstrip() + "\n"


def _render_provider(spec: ProviderSpec) -> list[str]:
    parameters = [f"{injection.name}: {injection.python_type}" for injection in spec.injections]
    signature = f"def {spec.provider_name}({', '.join(parameters)}) -> {spec.class_name}:"
    call_args = [injection.name for injection in spec.injections]
    return [signature, f"    return {spec.class_name}({', '.join(call_args)})"]


def _imports_for_specs(
    specs: list[ProviderSpec],
    type_modules: dict[str, str] | None = None,
) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    resolved_type_modules = (
        type_modules
        if type_modules is not None
        else {spec.class_name: spec.module for spec in specs}
    )
    for spec in specs:
        imports.setdefault(spec.module, set()).add(spec.class_name)
        for injection in spec.injections:
            type_name = base_type(injection.python_type)
            module = resolved_type_modules.get(type_name)
            if module is not None and should_import_type(type_name):
                imports.setdefault(module, set()).add(type_name)
    return imports


def _ordered_specs(specs: list[ProviderSpec]) -> list[ProviderSpec]:
    if provider_name_collisions_from_specs(specs):
        return sorted(specs, key=lambda spec: (spec.provider_name, spec.class_name, spec.identity))
    dependencies = _provider_dependencies(specs)
    by_provider_name = {spec.provider_name: spec for spec in specs}
    pending = set(dependencies)
    ordered: list[ProviderSpec] = []
    while pending:
        ready = sorted(
            (
                provider_name
                for provider_name in pending
                if all(dep not in pending for dep in dependencies[provider_name])
            ),
        )
        if not ready:
            ordered.extend(by_provider_name[name] for name in sorted(pending))
            break
        for provider_name in ready:
            pending.remove(provider_name)
            ordered.append(by_provider_name[provider_name])
    return ordered


def provider_name_collisions_from_specs(specs: list[ProviderSpec]) -> dict[str, list[ProviderSpec]]:
    specs_by_name: dict[str, list[ProviderSpec]] = {}
    for spec in specs:
        specs_by_name.setdefault(spec.provider_name, []).append(spec)
    return {
        provider_name: grouped_specs
        for provider_name, grouped_specs in specs_by_name.items()
        if len({spec.identity for spec in grouped_specs}) > 1
    }


def _provider_dependencies(specs: list[ProviderSpec]) -> dict[str, list[str]]:
    by_identity = {_normalize_identity(spec.identity): spec for spec in specs}
    dependencies: dict[str, list[str]] = {}
    for spec in specs:
        dependencies[spec.provider_name] = [
            by_identity[_normalize_identity(injection.name)].provider_name
            for injection in spec.injections
            if _normalize_identity(injection.name) in by_identity
        ]
    return dependencies


def _injections_for_class(
    elements: list[WiringElement],
    class_index: int,
) -> list[ProviderInjectionSpec]:
    owned_elements: list[WiringElement] = []
    for element in elements[class_index + 1 :]:
        if element.kind == "class":
            break
        owned_elements.append(element)
    return _injections(owned_elements)


def _injections(elements: list[WiringElement]) -> list[ProviderInjectionSpec]:
    return [
        ProviderInjectionSpec(name=name, python_type=python_type)
        for name, python_type in injection_specs(elements)
    ]


def _constructor_parameters(path: Path, class_name: str) -> list[ProviderInjectionSpec]:
    return [
        ProviderInjectionSpec(name=name, python_type=python_type)
        for name, python_type in constructor_parameters(path, class_name)
    ]


def _merge_injections(
    constructor_params: list[ProviderInjectionSpec],
    sidecar_injections: list[ProviderInjectionSpec],
) -> list[ProviderInjectionSpec]:
    by_name = {injection.name: injection for injection in sidecar_injections}
    merged: list[ProviderInjectionSpec] = []
    for constructor_param in constructor_params:
        merged.append(by_name.pop(constructor_param.name, constructor_param))
    merged.extend(by_name[name] for name in sorted(by_name))
    return merged


def _normalize_identity(name: str) -> str:
    return name.lower().replace("_", "")


def _str(value: object, *, default: str) -> str:
    return value if isinstance(value, str) else default
