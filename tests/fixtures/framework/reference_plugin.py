"""Fictional reference framework plugin used by Tier 4 tests."""

from __future__ import annotations

from j2py.framework import (
    FrameworkContext,
    FrameworkPlugin,
    FrameworkTransformResult,
    InitParam,
)


class ReferenceFrameworkPlugin(FrameworkPlugin):
    name = "reference"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "MappedController"):
            return FrameworkTransformResult()
        return FrameworkTransformResult(
            prefix_lines=("@mapped_controller",),
            base_classes=("MappedControllerBase",),
            imports=(
                "from tests.fixtures.framework.shims import "
                "MappedControllerBase, mapped_controller",
            ),
            metadata={"controller": ctx.py_name},
            handled=True,
        )

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "InjectDep"):
            return FrameworkTransformResult()
        return FrameworkTransformResult(
            prefix_lines=(f"        # injected by reference plugin: {ctx.py_type} {ctx.py_name}",),
            init_params=(InitParam(ctx.py_name, ctx.py_type or "object"),),
            metadata={"inject": {"field": ctx.py_name, "python_type": ctx.py_type}},
            handled=True,
        )

    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        route = _annotation(ctx, "MappedRoute")
        if route is None:
            return FrameworkTransformResult()
        path = route.values.get("value", "/" + ctx.py_name)
        return FrameworkTransformResult(
            prefix_lines=(f'    @mapped_route("{path}")',),
            imports=("from tests.fixtures.framework.shims import mapped_route",),
            metadata={"route": {"path": path, "handler": ctx.py_name}},
            handled=True,
        )


class ThrowingFrameworkPlugin(FrameworkPlugin):
    name = "throwing"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if _has_annotation(ctx, "MappedController"):
            raise RuntimeError("boom")
        return FrameworkTransformResult()

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if _has_annotation(ctx, "InjectDep"):
            raise RuntimeError("boom")
        return FrameworkTransformResult()

    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if _has_annotation(ctx, "MappedRoute"):
            raise RuntimeError("boom")
        return FrameworkTransformResult()


class EmptyMetadataFrameworkPlugin(ReferenceFrameworkPlugin):
    name = "empty-metadata"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "MappedController"):
            return FrameworkTransformResult()
        return FrameworkTransformResult(prefix_lines=("# handled without metadata",), handled=True)


class InvalidMetadataFrameworkPlugin(ReferenceFrameworkPlugin):
    name = "invalid-metadata"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "MappedController"):
            return FrameworkTransformResult()
        return FrameworkTransformResult(
            prefix_lines=("# handled with invalid metadata",),
            metadata={"bad": object()},
            handled=True,
        )


class CircularMetadataFrameworkPlugin(ReferenceFrameworkPlugin):
    name = "circular-metadata"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "MappedController"):
            return FrameworkTransformResult()
        metadata: dict[str, object] = {}
        metadata["self"] = metadata
        return FrameworkTransformResult(
            prefix_lines=("# handled with circular metadata",),
            metadata=metadata,
            handled=True,
        )


class RawStringFrameworkPlugin(ReferenceFrameworkPlugin):
    name = "raw-string"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "MappedController"):
            return FrameworkTransformResult()
        return FrameworkTransformResult(prefix_lines="@bad_decorator", handled=True)


class MultipleInitParamsFrameworkPlugin(ReferenceFrameworkPlugin):
    name = "multiple-init-params"

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "InjectDep"):
            return FrameworkTransformResult()
        py_type = ctx.py_type or "object"
        return FrameworkTransformResult(
            prefix_lines=(f"        # injected by multi-param plugin: {ctx.py_name}",),
            init_params=(
                InitParam(ctx.py_name, py_type),
                InitParam(f"{ctx.py_name}_extra", py_type),
            ),
            handled=True,
        )


def _has_annotation(ctx: FrameworkContext, simple_name: str) -> bool:
    return _annotation(ctx, simple_name) is not None


def _annotation(ctx: FrameworkContext, simple_name: str):
    for annotation in ctx.annotations:
        if annotation.simple_name == simple_name:
            return annotation
    return None
