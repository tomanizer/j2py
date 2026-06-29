"""FastAPI wiring generation target."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from j2py.wire.schema import WiringElement, WiringSidecar
from j2py.wire.targets.common import (
    GENERATED_HEADER,
    as_bool,
    as_int,
    as_str,
    base_type,
    injection_specs,
    should_import_type,
    type_modules,
)
from j2py.wiring_contract import translate_field_name


@dataclass(frozen=True)
class InjectionSpec:
    name: str
    python_type: str


@dataclass(frozen=True)
class RouteParameterSpec:
    name: str
    python_type: str
    required: bool
    source: str


@dataclass(frozen=True)
class RequestBodySpec:
    name: str
    python_type: str


@dataclass(frozen=True)
class RouteSpec:
    function_name: str
    http_method: str
    path: str
    status_code: int
    parameters: list[RouteParameterSpec]
    request_body: RequestBodySpec | None


@dataclass(frozen=True)
class ControllerSpec:
    class_name: str
    module: str
    router_prefix: str
    router_stem: str
    injections: list[InjectionSpec]
    routes: list[RouteSpec]


class FastAPITarget:
    """Generate FastAPI wiring modules from Spring sidecar metadata."""

    def __init__(self, *, translated_root: Path) -> None:
        self.translated_root = translated_root

    def generate(self, sidecars: list[WiringSidecar], output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        controllers = self._controllers(sidecars)
        generated: list[Path] = []
        for controller in controllers:
            path = output_dir / f"{controller.router_stem}_wiring.py"
            path.write_text(self._render_router(controller, sidecars), encoding="utf-8")
            generated.append(path)
        app_path = output_dir / "app_wiring.py"
        app_path.write_text(
            self._render_app_wiring(controllers, output_package=output_dir.name),
            encoding="utf-8",
        )
        generated.append(app_path)
        return generated

    def _controllers(self, sidecars: list[WiringSidecar]) -> list[ControllerSpec]:
        controllers: list[ControllerSpec] = []
        for sidecar in sidecars:
            controller_elements = [
                element
                for element in sidecar.elements
                if element.kind == "class" and element.spring.get("role") == "controller"
            ]
            for element in controller_elements:
                module = sidecar.python_module(self.translated_root)
                router_prefix = as_str(element.spring.get("router_prefix"), default="")
                controllers.append(
                    ControllerSpec(
                        class_name=element.python_name,
                        module=module,
                        router_prefix=router_prefix,
                        router_stem=Path(sidecar.output).stem,
                        injections=_injections(sidecar.elements),
                        routes=_routes(sidecar.elements),
                    ),
                )
        return controllers

    def _render_router(self, controller: ControllerSpec, sidecars: list[WiringSidecar]) -> str:
        imports = _imports_for_controller(controller, sidecars, self.translated_root)
        lines = [
            GENERATED_HEADER,
            "from __future__ import annotations",
            "",
            "from fastapi import APIRouter, Depends",
            "from sqlalchemy.orm import Session",
            "",
        ]
        for module in sorted(imports):
            names = ", ".join(sorted(imports[module]))
            lines.append(f"from {module} import {names}")
        lines.extend(
            [
                "",
                f"router = APIRouter(prefix={_literal(controller.router_prefix)}, "
                f"tags=[{_literal(_router_tag(controller))}])",
                "",
                "",
                "def get_session() -> Session:",
                "    # TODO(j2py): replace with your session factory",
                '    raise NotImplementedError("Configure the SQLAlchemy session factory")',
                "",
                "",
            ],
        )
        for injection in controller.injections:
            lines.extend(_render_provider(injection))
            lines.extend(["", ""])
        lines.extend(_render_controller_provider(controller))
        for route in controller.routes:
            lines.extend(["", ""])
            lines.extend(_render_route(controller, route))
        return "\n".join(lines).rstrip() + "\n"

    def _render_app_wiring(self, controllers: list[ControllerSpec], *, output_package: str) -> str:
        lines = [
            GENERATED_HEADER,
            "from __future__ import annotations",
            "",
            "from fastapi import FastAPI",
            "",
        ]
        for controller in controllers:
            alias = f"{controller.router_stem}_router"
            lines.append(
                f"from {output_package}.{controller.router_stem}_wiring import router as {alias}",
            )
        lines.extend(["", "", "def register_routes(app: FastAPI) -> None:"])
        if controllers:
            for controller in controllers:
                lines.append(f"    app.include_router({controller.router_stem}_router)")
        else:
            lines.append("    pass")
        return "\n".join(lines).rstrip() + "\n"


def _imports_for_controller(
    controller: ControllerSpec,
    sidecars: list[WiringSidecar],
    translated_root: Path,
) -> dict[str, set[str]]:
    modules_by_type = type_modules(sidecars, translated_root)
    imports: dict[str, set[str]] = {controller.module: {controller.class_name}}
    for type_name in _referenced_types(controller):
        module = modules_by_type.get(type_name, controller.module)
        imports.setdefault(module, set()).add(type_name)
    return imports


def _referenced_types(controller: ControllerSpec) -> set[str]:
    types = {injection.python_type for injection in controller.injections}
    for route in controller.routes:
        for parameter in route.parameters:
            types.add(parameter.python_type)
        if route.request_body is not None:
            types.add(route.request_body.python_type)
    return {base_type(type_name) for type_name in types if should_import_type(type_name)}


def _injections(elements: list[WiringElement]) -> list[InjectionSpec]:
    return [
        InjectionSpec(name=name, python_type=python_type)
        for name, python_type in injection_specs(elements)
    ]


def _routes(elements: list[WiringElement]) -> list[RouteSpec]:
    routes: list[RouteSpec] = []
    for element in elements:
        route = element.spring.get("route")
        if not isinstance(route, dict):
            continue
        request_body = _request_body(route.get("request_body"))
        routes.append(
            RouteSpec(
                function_name=as_str(route.get("handler"), default=element.python_name),
                http_method=as_str(route.get("http_method"), default="GET"),
                path=as_str(route.get("path"), default=""),
                status_code=as_int(route.get("status_code"), default=200),
                parameters=_parameters(route.get("parameters")),
                request_body=request_body,
            ),
        )
    return routes


def _parameters(value: object) -> list[RouteParameterSpec]:
    if not isinstance(value, list):
        return []
    parameters: list[RouteParameterSpec] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        parameters.append(
            RouteParameterSpec(
                name=as_str(item.get("name"), default="param"),
                python_type=as_str(item.get("python_type"), default="object"),
                required=as_bool(item.get("required"), default=True),
                source=as_str(item.get("source"), default="unknown"),
            ),
        )
    return parameters


def _request_body(value: object) -> RequestBodySpec | None:
    if not isinstance(value, dict):
        return None
    return RequestBodySpec(
        name=as_str(value.get("name"), default="body"),
        python_type=as_str(value.get("python_type"), default="object"),
    )


def _render_provider(injection: InjectionSpec) -> list[str]:
    provider_name = f"get_{injection.name}"
    return [
        f"def {provider_name}(session: Session = Depends(get_session)) -> {injection.python_type}:",
        f"    return {injection.python_type}(session)",
    ]


def _render_controller_provider(controller: ControllerSpec) -> list[str]:
    provider_name = f"get_{translate_field_name(controller.class_name)}"
    if not controller.injections:
        return [
            f"def {provider_name}() -> {controller.class_name}:",
            f"    return {controller.class_name}()",
        ]
    lines = [f"def {provider_name}("]
    for injection in controller.injections:
        lines.append(
            f"    {injection.name}: {injection.python_type} = Depends(get_{injection.name}),",
        )
    lines.extend(
        [
            f") -> {controller.class_name}:",
            f"    return {controller.class_name}("
            f"{', '.join(injection.name for injection in controller.injections)})",
        ],
    )
    return lines


def _render_route(controller: ControllerSpec, route: RouteSpec) -> list[str]:
    method = route.http_method.lower()
    decorator = f"@router.{method}({_literal(route.path)}"
    if route.status_code != 200:
        decorator += f", status_code={route.status_code}"
    decorator += ")"
    parameters = _route_signature_parameters(controller, route)
    call_args = _route_call_arguments(route)
    return [
        decorator,
        f"def {route.function_name}(",
        *[f"    {parameter}," for parameter in parameters],
        "):",
        f"    return controller.{route.function_name}({', '.join(call_args)})",
    ]


def _route_signature_parameters(controller: ControllerSpec, route: RouteSpec) -> list[str]:
    required: list[str] = []
    optional: list[str] = []
    for parameter in route.parameters:
        if parameter.source not in {"path", "query"}:
            continue
        if parameter.required:
            required.append(f"{parameter.name}: {parameter.python_type}")
        else:
            optional.append(f"{parameter.name}: {parameter.python_type} | None = None")
    if route.request_body is not None:
        required.append(f"{route.request_body.name}: {route.request_body.python_type}")
    required.extend(optional)
    required.append(
        f"controller: {controller.class_name} = Depends("
        f"get_{translate_field_name(controller.class_name)})",
    )
    return required


def _route_call_arguments(route: RouteSpec) -> list[str]:
    arguments = [
        parameter.name for parameter in route.parameters if parameter.source in {"path", "query"}
    ]
    if route.request_body is not None:
        arguments.append(route.request_body.name)
    return arguments


def _router_tag(controller: ControllerSpec) -> str:
    if controller.router_prefix:
        return controller.router_prefix.strip("/").split("/")[-1] or controller.router_stem
    return controller.router_stem


def _literal(value: str) -> str:
    return json.dumps(value)
