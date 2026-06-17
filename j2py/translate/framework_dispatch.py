"""Single dispatch point for Tier 4 framework plugins and Tier 2 annotation maps."""

from __future__ import annotations

import json

from j2py.config.loader import TranslationConfig
from j2py.framework import (
    FrameworkAnnotation,
    FrameworkContext,
    FrameworkMetadataRecord,
    FrameworkParam,
    FrameworkPlugin,
    FrameworkTransformResult,
    InitParam,
)
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.class_model import FieldInfo, ParameterInfo
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.framework_annotations import (
    annotation_full_name,
    annotation_simple_name,
    annotation_template_values,
    class_annotation_mapping,
    field_annotation_comment_lines,
    field_init_parameter,
    method_annotation_decorator_lines,
)


def resolve_class(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    java_name: str,
    py_name: str,
    indent: str = "",
) -> FrameworkTransformResult:
    ctx = FrameworkContext(
        node=node,
        element_kind="class",
        element_name=py_name,
        java_name=java_name,
        py_name=py_name,
        annotations=_framework_annotations(node),
        diagnostics=diagnostics,
    )
    result = _resolve_plugin(ctx, cfg.framework_plugins, "transform_class")
    if result is not None:
        return result

    mapping = class_annotation_mapping(node, cfg, diagnostics, indent=indent)
    return FrameworkTransformResult(
        prefix_lines=tuple(mapping.decorators),
        base_classes=tuple(mapping.bases),
    )


def resolve_field(
    field: FieldInfo,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    indent: str = "",
) -> FrameworkTransformResult:
    ctx = FrameworkContext(
        node=field.node,
        element_kind="field",
        element_name=field.py_name,
        java_name=field.name,
        py_name=field.py_name,
        annotations=_framework_annotations(field.node),
        diagnostics=diagnostics,
        java_type=field.java_type,
        py_type=field.py_type,
    )
    result = _resolve_plugin(ctx, cfg.framework_plugins, "transform_field")
    if result is not None:
        return result

    init_param = field_init_parameter(field, cfg, diagnostics)
    init_params = (
        (InitParam(py_name=init_param.py_name, py_type=init_param.py_type),)
        if init_param is not None
        else ()
    )
    return FrameworkTransformResult(
        prefix_lines=tuple(field_annotation_comment_lines(field, cfg, diagnostics, indent=indent)),
        init_params=init_params,
    )


def resolve_method(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    java_name: str,
    py_name: str,
    indent: str,
) -> FrameworkTransformResult:
    from j2py.translate.class_methods import parameter_infos, return_type

    params = tuple(_framework_param(param) for param in parameter_infos(node, cfg))
    ctx = FrameworkContext(
        node=node,
        element_kind="method" if node.type == "method_declaration" else "constructor",
        element_name=py_name,
        java_name=java_name,
        py_name=py_name,
        annotations=_framework_annotations(node),
        diagnostics=diagnostics,
        py_type="None" if node.type == "constructor_declaration" else return_type(node, cfg),
        parameters=params,
    )
    result = _resolve_plugin(ctx, cfg.framework_plugins, "transform_method")
    if result is not None:
        return result

    return FrameworkTransformResult(
        prefix_lines=tuple(
            method_annotation_decorator_lines(node, cfg, diagnostics, indent=indent),
        ),
    )


def _safe_invoke(
    plugin: FrameworkPlugin,
    hook: str,
    ctx: FrameworkContext,
) -> FrameworkTransformResult:
    try:
        result = getattr(plugin, hook)(ctx)
    except Exception as exc:
        ctx.diagnostics.warn(
            ctx.node,
            reason=f"framework plugin {plugin.name!r} raised in {hook}: {exc!r}",
        )
        return FrameworkTransformResult()
    if not isinstance(result, FrameworkTransformResult):
        ctx.diagnostics.warn(
            ctx.node,
            reason=(
                f"framework plugin {plugin.name!r} returned invalid result "
                f"in {hook}: {type(result).__name__}"
            ),
        )
        return FrameworkTransformResult()
    for field_name in ("prefix_lines", "base_classes", "imports"):
        if isinstance(getattr(result, field_name), str):
            ctx.diagnostics.warn(
                ctx.node,
                reason=(
                    f"framework plugin {plugin.name!r} returned a raw string "
                    f"instead of a tuple of strings for {field_name} in {hook}"
                ),
            )
            return FrameworkTransformResult()
    return result


def _resolve_plugin(
    ctx: FrameworkContext,
    plugins: list[FrameworkPlugin],
    hook: str,
) -> FrameworkTransformResult | None:
    for plugin in plugins:
        result = _safe_invoke(plugin, hook, ctx)
        if not result.handled:
            continue
        _register_imports(result, ctx.diagnostics)
        _record_metadata(plugin, result, ctx)
        ctx.diagnostics.record(
            ctx.node,
            supported=True,
            reason=f"framework plugin {plugin.name!r} handled {ctx.element_kind} {ctx.py_name}",
        )
        return result
    return None


def _framework_annotations(node: JavaNode) -> tuple[FrameworkAnnotation, ...]:
    annotations: list[FrameworkAnnotation] = []
    for annotation in annotation_nodes(node):
        full_name = annotation_full_name(annotation)
        simple_name = annotation_simple_name(annotation)
        if full_name is None or simple_name is None:
            continue
        annotations.append(
            FrameworkAnnotation(
                name=full_name,
                simple_name=simple_name,
                values=annotation_template_values(annotation),
            ),
        )
    return tuple(annotations)


def _framework_param(param: ParameterInfo) -> FrameworkParam:
    return FrameworkParam(
        java_name=param.raw_name,
        py_name=param.py_name,
        java_type=param.java_type,
        py_type=param.py_type,
    )


def _register_imports(
    result: FrameworkTransformResult,
    diagnostics: TranslationDiagnostics,
) -> None:
    for line in result.imports:
        stripped = line.strip()
        if stripped:
            diagnostics.imports.need_line(stripped)


def _record_metadata(
    plugin: FrameworkPlugin,
    result: FrameworkTransformResult,
    ctx: FrameworkContext,
) -> None:
    if not result.metadata:
        return
    metadata = dict(result.metadata)
    try:
        json.dumps(metadata, sort_keys=True)
    except (TypeError, ValueError) as exc:
        ctx.diagnostics.warn(
            ctx.node,
            reason=(
                f"framework plugin {plugin.name!r} returned non-JSON-serializable "
                f"metadata for {ctx.element_kind} {ctx.py_name}: {exc}"
            ),
        )
        return
    ctx.diagnostics.framework_metadata.append(
        FrameworkMetadataRecord(
            plugin=plugin.name,
            kind=ctx.element_kind,
            java_name=ctx.java_name,
            python_name=ctx.py_name,
            annotations=ctx.annotations,
            metadata=metadata,
        ),
    )
