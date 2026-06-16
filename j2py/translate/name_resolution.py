"""Deterministic Java identifier binding for the rule translator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from j2py.translate.rules.imports import java_import_policy
from j2py.translate.rules.imports import (
    python_binding_from_import_map as _python_binding_from_import_map,
)
from j2py.translate.rules.naming import translate_class_name, translate_field_name

if TYPE_CHECKING:
    from j2py.analyze.symbols import FileSymbols
    from j2py.config.loader import TranslationConfig
    from j2py.parse.java_ast import JavaNode, ParsedFile
    from j2py.translate.diagnostics import TranslationContext


ResolvedNameKind = Literal[
    "expression_alias",
    "static_field_alias",
    "parameter",
    "local",
    "field",
    "imported_type",
    "containing_type",
    "nested_type",
    "package_type",
    "compilation_unit_type",
    "unknown",
]

TypeBindingSource = Literal[
    "explicit_import",
    "drop_import",
    "import_map",
    "java_lang_builtin",
    "platform_placeholder",
    "external_placeholder",
    "package",
    "compilation_unit",
]


@dataclass(frozen=True)
class ResolvedName:
    raw_name: str
    python_name: str
    kind: ResolvedNameKind
    import_line: str | None = None
    is_type_reference: bool = False
    is_static_value: bool = False
    reason: str = ""


@dataclass(frozen=True)
class TypeBinding:
    raw_name: str
    python_name: str
    import_line: str | None = None
    source: TypeBindingSource = "explicit_import"


@dataclass(frozen=True)
class FileNameBindings:
    package_name: str = ""
    imported_types: dict[str, TypeBinding] = field(default_factory=dict)
    compilation_unit_types: set[str] = field(default_factory=set)
    static_field_aliases: dict[str, str] = field(default_factory=dict)
    static_method_imports: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NameScope:
    expression_aliases: dict[str, str] = field(default_factory=dict)
    static_field_aliases: dict[str, str] = field(default_factory=dict)
    param_names: set[str] = field(default_factory=set)
    local_names: set[str] = field(default_factory=set)
    class_fields: set[str] = field(default_factory=set)
    class_field_types: dict[str, str] = field(default_factory=dict)
    in_instance_method: bool = False
    in_method: bool = False
    containing_class_name: str | None = None
    nested_class_names: set[str] = field(default_factory=set)
    snake_case_fields: bool = True


class NameResolver:
    """Resolves the current deterministic subset of Java identifier bindings."""

    def __init__(self, bindings: FileNameBindings) -> None:
        self.bindings = bindings

    @classmethod
    def empty(cls) -> NameResolver:
        return cls(FileNameBindings())

    def resolve_identifier(self, raw_name: str, scope: NameScope) -> ResolvedName:
        if raw_name in scope.expression_aliases:
            return ResolvedName(
                raw_name=raw_name,
                python_name=scope.expression_aliases[raw_name],
                kind="expression_alias",
                reason="expression alias binding",
            )

        static_alias = scope.static_field_aliases.get(
            raw_name,
            self.bindings.static_field_aliases.get(raw_name),
        )
        if static_alias is not None:
            return ResolvedName(
                raw_name=raw_name,
                python_name=static_alias,
                kind="static_field_alias",
                is_static_value=True,
                reason="static field alias binding",
            )

        py_name = translate_field_name(raw_name, snake_case=scope.snake_case_fields)
        if raw_name in scope.param_names:
            return ResolvedName(
                raw_name=raw_name,
                python_name=py_name,
                kind="parameter",
                reason="parameter shadows type-like bindings",
            )
        if raw_name in scope.local_names:
            return ResolvedName(
                raw_name=raw_name,
                python_name=py_name,
                kind="local",
                reason="local shadows type-like bindings",
            )

        if raw_name in scope.class_field_types:
            return ResolvedName(
                raw_name=raw_name,
                python_name=self._field_python_name(raw_name, py_name, scope),
                kind="field",
                reason="class field binding",
            )

        imported_type = self.bindings.imported_types.get(raw_name)
        if imported_type is not None:
            return ResolvedName(
                raw_name=raw_name,
                python_name=imported_type.python_name,
                kind="imported_type",
                import_line=imported_type.import_line,
                is_type_reference=True,
                reason=f"{imported_type.source} type binding",
            )

        if raw_name[:1].isupper() and not raw_name.isupper():
            class_name = translate_class_name(raw_name)
            if class_name == scope.containing_class_name:
                return ResolvedName(
                    raw_name=raw_name,
                    python_name=class_name,
                    kind="containing_type",
                    is_type_reference=True,
                    reason="containing type binding",
                )
            if class_name in scope.nested_class_names:
                return ResolvedName(
                    raw_name=raw_name,
                    python_name=class_name,
                    kind="nested_type",
                    is_type_reference=True,
                    reason="nested type binding",
                )
            if self.bindings.package_name:
                return ResolvedName(
                    raw_name=raw_name,
                    python_name=class_name,
                    kind="package_type",
                    import_line=(
                        f"from {self.bindings.package_name}.{class_name} import {class_name}"
                    ),
                    is_type_reference=True,
                    reason="same-package type fallback",
                )
            if class_name in self.bindings.compilation_unit_types:
                return ResolvedName(
                    raw_name=raw_name,
                    python_name=class_name,
                    kind="compilation_unit_type",
                    import_line=f"from {class_name} import {class_name}",
                    is_type_reference=True,
                    reason="compilation-unit type fallback",
                )

        if raw_name in scope.class_fields and scope.in_instance_method:
            return ResolvedName(
                raw_name=raw_name,
                python_name=f"self.{py_name}",
                kind="field",
                reason="instance field fallback",
            )

        return ResolvedName(
            raw_name=raw_name,
            python_name=py_name,
            kind="unknown",
            reason="value-name fallback",
        )

    @staticmethod
    def _field_python_name(raw_name: str, py_name: str, scope: NameScope) -> str:
        if scope.in_instance_method and raw_name in scope.class_fields:
            return f"self.{py_name}"
        if (
            scope.in_method
            and raw_name not in scope.class_fields
            and scope.containing_class_name is not None
        ):
            return f"{scope.containing_class_name}.{py_name}"
        return py_name


def scope_from_context(ctx: TranslationContext) -> NameScope:
    return NameScope(
        expression_aliases=ctx.expression_aliases,
        static_field_aliases=ctx.static_field_aliases,
        param_names=ctx.param_names,
        local_names=ctx.local_names,
        class_fields=ctx.class_fields,
        class_field_types=ctx.class_field_types,
        in_instance_method=ctx.in_instance_method,
        in_method=ctx.in_method,
        containing_class_name=ctx.containing_class_name,
        nested_class_names=ctx.nested_class_names,
        snake_case_fields=ctx.cfg.snake_case_fields,
    )


def build_file_name_bindings(
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
    *,
    static_field_aliases: dict[str, str] | None = None,
    static_method_imports: dict[str, str] | None = None,
) -> FileNameBindings:
    return FileNameBindings(
        package_name=symbols.package,
        imported_types=imported_type_bindings(parsed, cfg),
        compilation_unit_types={translate_class_name(cls.name) for cls in symbols.classes},
        static_field_aliases=dict(static_field_aliases or {}),
        static_method_imports=dict(static_method_imports or {}),
    )


def imported_type_bindings(
    parsed: ParsedFile,
    cfg: TranslationConfig,
) -> dict[str, TypeBinding]:
    bindings: dict[str, TypeBinding] = {}
    for java_import in parsed.root.find_all("import_declaration"):
        if is_static_import(java_import):
            continue
        imported_name = java_import_name(java_import)
        if not imported_name:
            continue
        raw_name = imported_name.rsplit(".", 1)[-1]
        policy = java_import_policy(imported_name, cfg)
        if policy is not None:
            if policy.source == "import_map" and not policy.import_lines:
                continue
            import_line = (
                "\n".join(policy.import_lines)
                if policy.source in {"platform_placeholder", "external_placeholder"}
                else ""
            ) or None
            bindings[raw_name] = TypeBinding(
                raw_name=raw_name,
                python_name=policy.python_name,
                import_line=import_line,
                source=policy.source,
            )
            continue
        py_name = translate_class_name(raw_name)
        package, _, _ = imported_name.rpartition(".")
        bindings[raw_name] = TypeBinding(
            raw_name=raw_name,
            python_name=py_name,
            import_line=f"from {package}.{py_name} import {py_name}" if package else None,
        )
    return bindings


def python_binding_from_import_map(import_text: str) -> str | None:
    return _python_binding_from_import_map(import_text)


def java_import_name(node: JavaNode) -> str:
    for child in node.walk():
        if child.type in {"scoped_identifier", "identifier"}:
            return child.text
    return ""


def is_static_import(node: JavaNode) -> bool:
    return any(child.type == "static" for child in node.children)
