"""Framework-neutral provider generation target."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from j2py.wire.schema import WiringElement, WiringSidecar
from j2py.wire.targets.common import GENERATED_HEADER
from j2py.wiring_contract import translate_field_name

PROVIDERS_FILENAME = "providers.py"
_BUILTIN_TYPES = {
    "Any",
    "bool",
    "bytes",
    "dict",
    "float",
    "int",
    "list",
    "None",
    "object",
    "set",
    "str",
    "tuple",
}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
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
    needs_session: bool


class ProvidersTarget:
    """Generate plain Python factory functions from Spring wiring sidecars."""

    def __init__(self, *, translated_root: Path) -> None:
        self.translated_root = translated_root

    def generate(self, sidecars: list[WiringSidecar], output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / PROVIDERS_FILENAME
        path.write_text(
            render_providers(provider_specs(sidecars, self.translated_root)),
            encoding="utf-8",
        )
        return [path]


def provider_specs(sidecars: list[WiringSidecar], translated_root: Path) -> list[ProviderSpec]:
    """Return provider specs derived from class roles and local injection metadata."""
    specs: list[ProviderSpec] = []
    for sidecar in sidecars:
        module = sidecar.python_module(translated_root)
        injections = _injections(sidecar.elements)
        for element in sidecar.elements:
            if element.kind != "class":
                continue
            role = _str(element.spring.get("role"), default="")
            if role not in _PROVIDER_ROLES:
                continue
            identity = _provider_identity(element)
            specs.append(
                ProviderSpec(
                    identity=identity,
                    provider_name=f"get_{translate_field_name(identity)}",
                    class_name=element.python_name,
                    module=module,
                    role=role,
                    injections=injections,
                    needs_session=role == "repository" and not injections,
                ),
            )
    return _ordered_specs(specs)


def expected_provider_names(sidecars: list[WiringSidecar], translated_root: Path) -> set[str]:
    """Return generated provider function names for validation checks."""
    return {spec.provider_name for spec in provider_specs(sidecars, translated_root)}


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


def render_providers(specs: list[ProviderSpec]) -> str:
    """Render importable provider module source."""
    imports = _imports_for_specs(specs)
    lines = [
        GENERATED_HEADER,
        "from __future__ import annotations",
        "",
    ]
    if any(spec.needs_session for spec in specs):
        lines.extend(["from sqlalchemy.orm import Session", ""])
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
        lines.extend(["", "__all__: list[str] = []"])
    return "\n".join(lines).rstrip() + "\n"


def _render_provider(spec: ProviderSpec) -> list[str]:
    parameters: list[str] = []
    if spec.needs_session:
        parameters.append("session: Session")
    parameters.extend(f"{injection.name}: {injection.python_type}" for injection in spec.injections)
    signature = f"def {spec.provider_name}({', '.join(parameters)}) -> {spec.class_name}:"
    call_args = ["session"] if spec.needs_session else []
    call_args.extend(injection.name for injection in spec.injections)
    return [signature, f"    return {spec.class_name}({', '.join(call_args)})"]


def _imports_for_specs(specs: list[ProviderSpec]) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    type_modules = {spec.class_name: spec.module for spec in specs}
    for spec in specs:
        imports.setdefault(spec.module, set()).add(spec.class_name)
        for injection in spec.injections:
            type_name = _base_type(injection.python_type)
            module = type_modules.get(type_name)
            if module is not None and _should_import_type(type_name):
                imports.setdefault(module, set()).add(type_name)
    return imports


def _ordered_specs(specs: list[ProviderSpec]) -> list[ProviderSpec]:
    by_identity = {_normalize_identity(spec.identity): spec for spec in specs}
    dependencies = {
        spec.provider_name: [
            by_identity[_normalize_identity(injection.name)].provider_name
            for injection in spec.injections
            if _normalize_identity(injection.name) in by_identity
        ]
        for spec in specs
    }
    pending = {spec.provider_name: spec for spec in specs}
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
            ordered.extend(pending[name] for name in sorted(pending))
            break
        for provider_name in ready:
            ordered.append(pending.pop(provider_name))
    return ordered


def _provider_identity(element: WiringElement) -> str:
    component_name = element.spring.get("component_name")
    if isinstance(component_name, str) and component_name:
        return component_name
    return translate_field_name(element.python_name)


def _injections(elements: list[WiringElement]) -> list[ProviderInjectionSpec]:
    injections: list[ProviderInjectionSpec] = []
    for element in elements:
        inject = element.spring.get("inject")
        if not isinstance(inject, dict):
            continue
        injections.append(
            ProviderInjectionSpec(
                name=_str(inject.get("name"), default=translate_field_name(element.java_name)),
                python_type=_str(inject.get("type"), default="object"),
            ),
        )
    return injections


def _normalize_identity(name: str) -> str:
    return name.lower().replace("_", "")


def _base_type(type_name: str) -> str:
    return re.split(r"[\[|.]", type_name, maxsplit=1)[0].strip()


def _should_import_type(type_name: str) -> bool:
    base = _base_type(type_name)
    return bool(base and base not in _BUILTIN_TYPES and _IDENTIFIER_RE.match(base))


def _str(value: object, *, default: str) -> str:
    return value if isinstance(value, str) else default
