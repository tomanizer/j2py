"""Shared environment for class declaration translation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from j2py.parse.java_ast import JavaNode
from j2py.translate.name_resolution import NameResolver

if TYPE_CHECKING:
    from j2py.translate.member_resolution import JavaMemberBinding

_NodeKey = tuple[int, int, int, int, str]


@dataclass(frozen=True)
class ClassTranslationEnvironment:
    """Read-only cross-class translation context.

    Per-class mutable flags belong in ``ClassTranslationState``. This object carries the
    file/module indexes, inherited type facts, and import/name bindings that are shared
    across class declaration entry points.
    """

    inherited_class_field_types: dict[str, str] = field(default_factory=dict)
    inherited_class_field_java_types: dict[str, str] = field(default_factory=dict)
    inherited_declared_type_fields: dict[str, dict[str, str]] = field(default_factory=dict)
    inherited_declared_type_java_fields: dict[str, dict[str, str]] = field(default_factory=dict)
    inherited_declared_type_method_return_types: dict[str, dict[str, str]] = field(
        default_factory=dict,
    )
    static_field_aliases: dict[str, str] = field(default_factory=dict)
    static_method_imports: dict[str, str] = field(default_factory=dict)
    static_member_bindings: dict[str, JavaMemberBinding] = field(default_factory=dict)
    wildcard_static_imports: dict[str, str] = field(default_factory=dict)
    name_resolver: NameResolver = field(default_factory=NameResolver.empty)
    docstring_lines: list[str] | None = None
    outer_self_alias: str | None = None
    requires_outer_self: bool = False
    file_class_static_methods: dict[str, set[str]] = field(default_factory=dict)
    file_class_static_instance_aliases: dict[str, dict[str, str]] = field(default_factory=dict)
    file_class_declarations: dict[str, JavaNode] = field(default_factory=dict)
    module_class_static_methods: dict[str, set[str]] = field(default_factory=dict)
    module_class_static_instance_aliases: dict[str, dict[str, str]] = field(
        default_factory=dict,
    )
    module_class_declarations: dict[str, JavaNode] = field(default_factory=dict)
    pydantic_model_class_names: set[str] = field(default_factory=set)
    enclosing_static_dispatch: dict[str, str] = field(default_factory=dict)
    interface_type_var_maps: dict[_NodeKey, dict[str, str]] = field(default_factory=dict)

    def with_overrides(self, **changes: Any) -> ClassTranslationEnvironment:
        return replace(self, **changes)
