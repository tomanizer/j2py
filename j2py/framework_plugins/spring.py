"""Spring wiring metadata plugin."""

from __future__ import annotations

import re
from collections.abc import Mapping

from j2py.framework import (
    FrameworkAnnotation,
    FrameworkContext,
    FrameworkParam,
    FrameworkPlugin,
    FrameworkTransformResult,
    InitParam,
)
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.framework_annotations import (
    annotation_simple_name,
    annotation_template_values,
)
from j2py.translate.rules.naming import translate_field_name

_PROFILE_VERSION = 1
_CLASS_ROLES: Mapping[str, str] = {
    "RestController": "controller",
    "Controller": "controller",
    "Service": "service",
    "Repository": "repository",
    "Component": "component",
    "Configuration": "configuration",
}
_CLASS_MARKER_DECORATORS: Mapping[str, tuple[str, str]] = {
    "RestController": ("rest_controller", "rest_controller"),
    "Controller": ("controller", "controller"),
    "Service": ("service", "service"),
    "Repository": ("repository", "repository"),
    "Component": ("component", "component"),
    "Configuration": ("configuration", "configuration"),
}
_METHOD_MARKER_DECORATORS: Mapping[str, tuple[str, str]] = {
    "GetMapping": ("get_mapping", "get_mapping"),
    "PostMapping": ("post_mapping", "post_mapping"),
    "PutMapping": ("put_mapping", "put_mapping"),
    "DeleteMapping": ("delete_mapping", "delete_mapping"),
}
_HTTP_METHODS: Mapping[str, str] = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
}
_ROUTE_ANNOTATIONS = frozenset({*_HTTP_METHODS, "RequestMapping"})
_STATUS_CODE_NAMES: Mapping[str, int] = {
    "ACCEPTED": 202,
    "BAD_GATEWAY": 502,
    "BAD_REQUEST": 400,
    "CONFLICT": 409,
    "CREATED": 201,
    "FORBIDDEN": 403,
    "FOUND": 302,
    "GATEWAY_TIMEOUT": 504,
    "INTERNAL_SERVER_ERROR": 500,
    "METHOD_NOT_ALLOWED": 405,
    "MOVED_PERMANENTLY": 301,
    "NO_CONTENT": 204,
    "NOT_ACCEPTABLE": 406,
    "NOT_FOUND": 404,
    "NOT_MODIFIED": 304,
    "OK": 200,
    "PERMANENT_REDIRECT": 308,
    "PRECONDITION_FAILED": 412,
    "SEE_OTHER": 303,
    "SERVICE_UNAVAILABLE": 503,
    "TEMPORARY_REDIRECT": 307,
    "TOO_MANY_REQUESTS": 429,
    "UNAUTHORIZED": 401,
    "UNPROCESSABLE_ENTITY": 422,
    "UNSUPPORTED_MEDIA_TYPE": 415,
}
_STATUS_CODES: Mapping[str, int] = {
    **_STATUS_CODE_NAMES,
    **{f"HttpStatus.{name}": code for name, code in _STATUS_CODE_NAMES.items()},
}
_PATH_VARIABLE_RE = re.compile(r"\{([^{}]+)\}")


class SpringWiringPlugin(FrameworkPlugin):
    """Emit Spring v1 wiring metadata through the generic framework plugin contract."""

    name = "spring-wiring"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        role_annotation = _first_annotation(ctx.annotations, set(_CLASS_ROLES))
        request_mapping = _annotation(ctx.annotations, "RequestMapping")
        if role_annotation is None and request_mapping is None:
            return FrameworkTransformResult()

        spring: dict[str, object] = {"profile_version": _PROFILE_VERSION}
        if role_annotation is not None:
            spring["role"] = _CLASS_ROLES[role_annotation.simple_name]
            spring["component_name"] = _component_name(ctx.java_name, role_annotation.values)
        if request_mapping is not None:
            router_prefix = _annotation_path(request_mapping.values)
            if router_prefix:
                spring["router_prefix"] = _normalize_route_path(router_prefix)

        return FrameworkTransformResult(
            prefix_lines=_class_prefix_lines(ctx.annotations),
            imports=_class_imports(ctx.annotations),
            metadata={"spring": spring},
            handled=True,
        )

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        autowired = _annotation(ctx.annotations, "Autowired")
        if autowired is None:
            return FrameworkTransformResult()
        qualifier = _annotation(ctx.annotations, "Qualifier")

        spring = {
            "profile_version": _PROFILE_VERSION,
            "inject": {
                "name": ctx.py_name,
                "java_name": ctx.java_name,
                "type": ctx.py_type or ctx.java_type or "object",
                "source": "field",
                "required": _required(autowired.values if autowired is not None else {}),
                "qualifier": _qualifier(qualifier),
            },
        }
        prefix_lines = tuple(_field_comment_lines(ctx.annotations))
        init_params = (
            (InitParam(ctx.py_name, ctx.py_type or ctx.java_type or "object"),)
            if autowired is not None
            else ()
        )
        return FrameworkTransformResult(
            prefix_lines=prefix_lines,
            init_params=init_params,
            metadata={"spring": spring},
            handled=True,
        )

    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        route_annotation = _first_annotation(ctx.annotations, set(_ROUTE_ANNOTATIONS))
        response_status = _annotation(ctx.annotations, "ResponseStatus")
        if route_annotation is None and response_status is None:
            return FrameworkTransformResult()
        if route_annotation is None:
            return FrameworkTransformResult(
                prefix_lines=_method_prefix_lines(ctx.annotations),
                imports=_method_imports(ctx.annotations),
                handled=True,
            )

        route: dict[str, object] = {
            "http_method": _http_method(route_annotation),
            "path": _normalize_route_path(_annotation_path(route_annotation.values)),
            "handler": ctx.py_name,
            "status_code": _status_code(response_status) or 200,
        }
        parameters, request_body = _route_parameters(ctx)
        route["parameters"] = parameters
        route["request_body"] = request_body

        return FrameworkTransformResult(
            prefix_lines=_method_prefix_lines(ctx.annotations),
            imports=_method_imports(ctx.annotations),
            metadata={"spring": {"profile_version": _PROFILE_VERSION, "route": route}},
            handled=True,
        )


def _annotation(
    annotations: tuple[FrameworkAnnotation, ...],
    simple_name: str,
) -> FrameworkAnnotation | None:
    return _first_annotation(annotations, {simple_name})


def _first_annotation(
    annotations: tuple[FrameworkAnnotation, ...],
    simple_names: set[str],
) -> FrameworkAnnotation | None:
    for annotation in annotations:
        if annotation.simple_name in simple_names:
            return annotation
    return None


def _component_name(java_name: str, values: Mapping[str, str]) -> str:
    explicit = values.get("value") or values.get("name")
    if explicit:
        return explicit
    if len(java_name) > 1 and java_name[0].isupper() and java_name[1].isupper():
        return java_name
    return java_name[:1].lower() + java_name[1:] if java_name else ""


def _annotation_path(values: Mapping[str, str]) -> str:
    return values.get("value") or values.get("path") or ""


def _normalize_route_path(path: str) -> str:
    if not path:
        return ""
    rendered = path if path.startswith("/") else f"/{path}"
    return _PATH_VARIABLE_RE.sub(_normalize_path_variable, rendered)


def _normalize_path_variable(match: re.Match[str]) -> str:
    content = match.group(1)
    if ":" in content:
        var_name, regex = content.split(":", 1)
        return "{" + translate_field_name(var_name, snake_case=True) + ":" + regex + "}"
    return "{" + translate_field_name(content, snake_case=True) + "}"


def _class_prefix_lines(annotations: tuple[FrameworkAnnotation, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for annotation in annotations:
        if annotation.simple_name in _CLASS_MARKER_DECORATORS:
            decorator, _import_name = _CLASS_MARKER_DECORATORS[annotation.simple_name]
            lines.append(f"@{decorator}")
            continue
        if annotation.simple_name == "RequestMapping":
            lines.append(_request_mapping_decorator(annotation.values, indent=""))
    return tuple(lines)


def _class_imports(annotations: tuple[FrameworkAnnotation, ...]) -> tuple[str, ...]:
    names: set[str] = set()
    for annotation in annotations:
        if annotation.simple_name in _CLASS_MARKER_DECORATORS:
            names.add(_CLASS_MARKER_DECORATORS[annotation.simple_name][1])
        elif annotation.simple_name == "RequestMapping":
            names.add("request_mapping")
    return _runtime_imports(names)


def _method_prefix_lines(annotations: tuple[FrameworkAnnotation, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for annotation in annotations:
        if annotation.simple_name in _METHOD_MARKER_DECORATORS:
            decorator, _import_name = _METHOD_MARKER_DECORATORS[annotation.simple_name]
            lines.append(f'    @{decorator}("{_annotation_path(annotation.values)}")')
            continue
        if annotation.simple_name == "RequestMapping":
            lines.append(_request_mapping_decorator(annotation.values, indent="    "))
            continue
        if annotation.simple_name == "ResponseStatus":
            status = _status_code(annotation)
            if status is not None:
                lines.append(f"    @response_status({status})")
    return tuple(lines)


def _method_imports(annotations: tuple[FrameworkAnnotation, ...]) -> tuple[str, ...]:
    names: set[str] = set()
    for annotation in annotations:
        if annotation.simple_name in _METHOD_MARKER_DECORATORS:
            names.add(_METHOD_MARKER_DECORATORS[annotation.simple_name][1])
        elif annotation.simple_name == "RequestMapping":
            names.add("request_mapping")
        elif annotation.simple_name == "ResponseStatus" and _status_code(annotation) is not None:
            names.add("response_status")
    return _runtime_imports(names)


def _runtime_imports(names: set[str]) -> tuple[str, ...]:
    if not names:
        return ()
    return (f"from j2py_runtime import {', '.join(sorted(names))}",)


def _request_mapping_decorator(values: Mapping[str, str], *, indent: str) -> str:
    path = _annotation_path(values)
    method = _request_mapping_method(values)
    if method:
        return f'{indent}@request_mapping("{path}", method="{method}")'
    return f'{indent}@request_mapping("{path}")'


def _field_comment_lines(annotations: tuple[FrameworkAnnotation, ...]) -> list[str]:
    lines: list[str] = []
    if _annotation(annotations, "Autowired") is not None:
        lines.append("        # @Autowired")
    qualifier = _annotation(annotations, "Qualifier")
    if qualifier is not None:
        value = _qualifier(qualifier)
        suffix = f'("{value}")' if value else ""
        lines.append(f"        # @Qualifier{suffix}")
    return lines


def _http_method(annotation: FrameworkAnnotation) -> str:
    if annotation.simple_name in _HTTP_METHODS:
        return _HTTP_METHODS[annotation.simple_name]
    return _request_mapping_method(annotation.values) or "REQUEST"


def _request_mapping_method(values: Mapping[str, str]) -> str | None:
    raw = values.get("method")
    if raw is None:
        return None
    method = raw.rsplit(".", 1)[-1].strip("{} ")
    return method.upper() if method else None


def _status_code(annotation: FrameworkAnnotation | None) -> int | None:
    if annotation is None:
        return None
    raw = annotation.values.get("value") or annotation.values.get("code")
    if raw is None:
        return None
    normalized = raw.rsplit(".", 1)[-1].strip()
    if normalized.isdigit():
        return int(normalized)
    return _STATUS_CODES.get(normalized)


def _route_parameters(
    ctx: FrameworkContext,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    parameters: list[dict[str, object]] = []
    request_body: dict[str, object] | None = None
    param_nodes = _formal_parameter_nodes(ctx.node)
    for index, param in enumerate(ctx.parameters):
        node = param_nodes[index] if index < len(param_nodes) else None
        annotations = _parameter_annotations(node)
        path_variable = annotations.get("PathVariable")
        request_param = annotations.get("RequestParam")
        request_body_annotation = annotations.get("RequestBody")
        if path_variable is not None:
            parameters.append(_route_parameter(param, path_variable, source="path"))
        elif request_param is not None:
            parameters.append(_route_parameter(param, request_param, source="query"))
        elif request_body_annotation is not None:
            request_body = {
                "name": param.py_name,
                "java_name": param.java_name,
                "python_type": param.py_type,
                "required": True,
            }
        else:
            parameters.append(
                {
                    "name": param.py_name,
                    "java_name": param.java_name,
                    "source": "unknown",
                    "python_type": param.py_type,
                    "required": True,
                },
            )
    return parameters, request_body


def _formal_parameter_nodes(node: JavaNode) -> list[JavaNode]:
    params = node.child_by_field("parameters")
    if params is None:
        return []
    return [
        child
        for child in params.named_children
        if child.type in {"formal_parameter", "spread_parameter"}
    ]


def _parameter_annotations(node: JavaNode | None) -> dict[str, Mapping[str, str]]:
    if node is None:
        return {}
    annotations: dict[str, Mapping[str, str]] = {}
    for annotation in annotation_nodes(node):
        simple_name = annotation_simple_name(annotation)
        if simple_name is None:
            continue
        annotations[simple_name] = annotation_template_values(annotation)
    return annotations


def _route_parameter(
    param: FrameworkParam,
    values: Mapping[str, str],
    *,
    source: str,
) -> dict[str, object]:
    java_name = values.get("value") or values.get("name") or param.java_name
    return {
        "name": translate_field_name(java_name, snake_case=True),
        "java_name": param.java_name,
        "source": source,
        "python_type": param.py_type,
        "required": _required(values),
    }


def _required(values: Mapping[str, str]) -> bool:
    return "false" not in values.get("required", "true").lower()


def _qualifier(annotation: FrameworkAnnotation | None) -> str | None:
    if annotation is None:
        return None
    return annotation.values.get("value") or annotation.values.get("name")
