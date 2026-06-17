"""Public framework plugin contract for programmatic annotation lowering."""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from j2py.parse.java_ast import JavaNode
    from j2py.translate.diagnostics import TranslationDiagnostics


@dataclass(frozen=True)
class InitParam:
    py_name: str
    py_type: str


@dataclass(frozen=True)
class FrameworkAnnotation:
    name: str
    simple_name: str
    values: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class FrameworkParam:
    java_name: str
    py_name: str
    java_type: str
    py_type: str


@dataclass(frozen=True)
class FrameworkTransformResult:
    prefix_lines: tuple[str, ...] = ()
    base_classes: tuple[str, ...] = ()
    init_params: tuple[InitParam, ...] = ()
    imports: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    handled: bool = False


@dataclass
class FrameworkContext:
    node: JavaNode
    element_kind: str
    element_name: str
    java_name: str
    py_name: str
    annotations: tuple[FrameworkAnnotation, ...]
    diagnostics: TranslationDiagnostics
    java_type: str | None = None
    py_type: str | None = None
    parameters: tuple[FrameworkParam, ...] = ()


class FrameworkPlugin(ABC):  # noqa: B024 - no-op hooks are part of the public contract.
    """Base class for trusted framework lowering plugins."""

    name: str = "unnamed"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()

    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()
