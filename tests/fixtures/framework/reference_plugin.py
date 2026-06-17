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
            handled=True,
        )

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has_annotation(ctx, "InjectDep"):
            return FrameworkTransformResult()
        return FrameworkTransformResult(
            prefix_lines=(f"        # injected by reference plugin: {ctx.py_type} {ctx.py_name}",),
            init_params=(InitParam(ctx.py_name, ctx.py_type or "object"),),
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


def _has_annotation(ctx: FrameworkContext, simple_name: str) -> bool:
    return _annotation(ctx, simple_name) is not None


def _annotation(ctx: FrameworkContext, simple_name: str):
    for annotation in ctx.annotations:
        if annotation.simple_name == simple_name:
            return annotation
    return None
