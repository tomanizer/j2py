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
    from j2py.analyze.symbols import ClassSymbol, FileSymbols
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
    "file_type",
    "enum_constant",
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
    file_type_paths: dict[str, str] = field(default_factory=dict)
    enum_constant_paths: dict[str, str] = field(default_factory=dict)
    wildcard_static_method_owners: dict[str, str] = field(default_factory=dict)
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
    enclosing_class_fields: set[str] = field(default_factory=set)
    enclosing_class_field_types: dict[str, str] = field(default_factory=dict)
    outer_self_alias: str | None = None
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

        if (
            scope.outer_self_alias
            and scope.in_instance_method
            and raw_name in scope.enclosing_class_fields
            and raw_name not in scope.class_fields
        ):
            return ResolvedName(
                raw_name=raw_name,
                python_name=f"{scope.outer_self_alias}.{py_name}",
                kind="field",
                reason="enclosing instance field binding",
            )

        # A constant of a file-declared enum, brought into bare scope by a static
        # import (``import static Outer.Kind.*``), is reachable through its enum
        # (``Outer.Kind.DOT``) from a method body but is a class-body local inside the
        # enum itself, so only qualify in a method context.
        if scope.in_method:
            enum_path = self.bindings.enum_constant_paths.get(raw_name)
            if enum_path is not None:
                return ResolvedName(
                    raw_name=raw_name,
                    python_name=enum_path,
                    kind="enum_constant",
                    reason="file enum constant binding",
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
            # Nested types are reachable as bare locals inside a class body (where the
            # enclosing class name is not yet bound), so only qualify references that
            # appear inside a method body, where the bare name would be undefined.
            if scope.in_method:
                file_path = self.bindings.file_type_paths.get(class_name)
                if file_path is not None:
                    return ResolvedName(
                        raw_name=raw_name,
                        python_name=file_path,
                        kind="file_type",
                        is_type_reference=True,
                        reason="file-declared nested type binding",
                    )
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
        enclosing_class_fields=ctx.enclosing_class_fields,
        enclosing_class_field_types=ctx.enclosing_class_field_types,
        outer_self_alias=ctx.outer_self_alias,
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
    wildcard_static_imports: dict[str, str] | None = None,
    declared_type_method_return_types: dict[str, dict[str, str]] | None = None,
) -> FileNameBindings:
    compilation_unit_types = {translate_class_name(cls.name) for cls in symbols.classes}
    file_type_paths = _file_type_paths(symbols)
    return FileNameBindings(
        package_name=symbols.package,
        imported_types=imported_type_bindings(parsed, cfg),
        compilation_unit_types=compilation_unit_types,
        file_type_paths=file_type_paths,
        enum_constant_paths=_file_enum_constant_paths(parsed.root),
        wildcard_static_method_owners=_wildcard_static_method_owners(
            wildcard_static_imports or {},
            declared_type_method_return_types or {},
            file_type_paths,
            compilation_unit_types,
        ),
        static_field_aliases=dict(static_field_aliases or {}),
        static_method_imports=dict(static_method_imports or {}),
    )


def _wildcard_static_method_owners(
    wildcard_static_imports: dict[str, str],
    declared_type_method_return_types: dict[str, dict[str, str]],
    file_type_paths: dict[str, str],
    compilation_unit_types: set[str],
) -> dict[str, str]:
    """Map a wildcard-static-imported method name to its enclosing-qualified owner.

    ``import static Outer.Validators.*`` lets the source call ``nonNegative(...)`` bare.
    Most member contexts resolve this through their per-class wildcard maps, but some
    (merged/dispatched overload bodies) are built without them. Recording the owner at
    file scope — where the wildcard imports live — lets the call resolve in any context
    to ``Outer.Validators.non_negative(...)``. Only owners declared in this file are
    eligible; names that collide across owners are dropped so no owner is guessed.
    """
    owners: dict[str, str] = {}
    collisions: set[str] = set()
    for simple_owner in wildcard_static_imports:
        raw_owner = simple_owner.rsplit(".", 1)[-1]
        py_owner = translate_class_name(raw_owner)
        owner_path = file_type_paths.get(py_owner)
        if owner_path is None:
            if py_owner not in compilation_unit_types:
                continue
            owner_path = py_owner
        methods = declared_type_method_return_types.get(py_owner) or declared_type_method_return_types.get(
            raw_owner, {}
        )
        for java_method in methods:
            if java_method in owners and owners[java_method] != owner_path:
                collisions.add(java_method)
            owners[java_method] = owner_path
    for name in collisions:
        owners.pop(name, None)
    return owners


def _file_type_paths(symbols: FileSymbols) -> dict[str, str]:
    """Map each *nested* file-declared type's simple Python name to its enclosing path.

    Nested classes are not module globals in Python: a reference to ``Inner`` from
    anywhere other than its own class body resolves through the enclosing class
    (``Outer.Inner``), and it never needs a peer import because it lives in the same
    module as its encloser. This map records that enclosing-qualified path for every
    nested type so the resolver can qualify references and suppress bogus imports.

    Top-level types are intentionally excluded: the project emits one module per
    top-level class, so their resolution (bare reference vs. ``from X import X``) is
    owned by the existing containing/package/compilation-unit handling. Simple names
    that collide across distinct paths are dropped so the resolver falls back rather
    than guessing a qualification.
    """
    paths: dict[str, str] = {}
    collisions: set[str] = set()

    def walk(cls: ClassSymbol, prefix: str) -> None:
        py_name = translate_class_name(cls.name)
        qualified = f"{prefix}.{py_name}" if prefix else py_name
        if prefix:
            if py_name in paths and paths[py_name] != qualified:
                collisions.add(py_name)
            paths[py_name] = qualified
        for inner in cls.inner_classes:
            walk(inner, qualified)

    for cls in symbols.classes:
        walk(cls, "")
    for name in collisions:
        paths.pop(name, None)
    return paths


_TYPE_DECLARATION_NODES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    }
)


def _file_enum_constant_paths(root: JavaNode) -> dict[str, str]:
    """Map each file-declared enum constant's name to its enclosing-qualified path.

    A static import of an enum's constants (``import static Outer.Kind.*``) lets the
    Java source name them bare (``DOT``). In Python a constant is reached through its
    enum (``Outer.Kind.DOT``), so record that path for every enum constant declared in
    the file. Names that collide across enums are dropped so the resolver leaves them
    unqualified rather than guessing the wrong enum.
    """
    paths: dict[str, str] = {}
    collisions: set[str] = set()

    def nested_type_decls(body: JavaNode) -> list[JavaNode]:
        decls: list[JavaNode] = []
        for child in body.named_children:
            if child.type in _TYPE_DECLARATION_NODES:
                decls.append(child)
            elif child.type == "enum_body_declarations":
                decls.extend(c for c in child.named_children if c.type in _TYPE_DECLARATION_NODES)
        return decls

    def walk(type_node: JavaNode, prefix: str) -> None:
        name_node = type_node.child_by_field("name")
        if name_node is None:
            return
        qualified = translate_class_name(name_node.text)
        if prefix:
            qualified = f"{prefix}.{qualified}"
        body = type_node.child_by_field("body")
        if body is None:
            return
        if type_node.type == "enum_declaration":
            for child in body.named_children:
                if child.type != "enum_constant":
                    continue
                const_node = child.child_by_field("name")
                const_name = (
                    const_node.text
                    if const_node is not None
                    else child.text.split("(", 1)[0].strip()
                )
                const_path = f"{qualified}.{const_name}"
                if const_name in paths and paths[const_name] != const_path:
                    collisions.add(const_name)
                paths[const_name] = const_path
        for nested in nested_type_decls(body):
            walk(nested, qualified)

    for child in root.named_children:
        if child.type in _TYPE_DECLARATION_NODES:
            walk(child, "")
    for name in collisions:
        paths.pop(name, None)
    return paths


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
