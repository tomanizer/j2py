"""Member indexing, Javadoc, and static-dispatch helpers for class translation."""

from __future__ import annotations

from collections.abc import Iterable

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_model import TYPE_DECLARATION_NODES, _modifiers
from j2py.translate.comments import (
    is_comment,
    is_javadoc_comment,
    translate_comment,
    translate_javadoc_docstring,
)
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.name_resolution import NameResolver, NameScope
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_class_name, translate_method_name

_NodeKey = tuple[int, int, int, int, str]


def type_metadata_comment_lines(node: JavaNode, *, indent: str) -> list[str]:
    modifiers = _modifiers(node)
    lines: list[str] = []
    permits = permits_names(node)
    if "sealed" in modifiers:
        if permits:
            lines.append(f"{indent}# sealed: permits {', '.join(permits)}")
        else:
            lines.append(f"{indent}# sealed")
    if "non-sealed" in modifiers:
        lines.append(f"{indent}# non-sealed")
    if "final" in modifiers and node.type == "class_declaration":
        lines.append(f"{indent}# final")
    return lines


def sealed_type_alias_lines(
    node: JavaNode,
    body: JavaNode | None,
    class_name: str,
    *,
    indent: str,
) -> list[str]:
    permits = permits_names(node)
    if not permits or body is None:
        return []
    nested_names = direct_nested_type_names(body)
    if any(name not in nested_names for name in permits):
        return []
    alias = f"{class_name}Permitted"
    return [f"{indent}{alias} = {' | '.join(permits)}  # sealed permitted subclasses"]


def permits_names(node: JavaNode) -> list[str]:
    permits_node = first_child_by_type(node, "permits")
    if permits_node is None:
        return []
    names: list[str] = []
    for child in permits_node.walk():
        if child.type in {"type_identifier", "scoped_type_identifier", "identifier"}:
            names.append(translate_class_name(child.text))
    return names


def direct_nested_type_names(body: JavaNode) -> set[str]:
    names: set[str] = set()
    for child in direct_nested_type_declarations(body):
        type_name = type_name_of(node=child)
        if type_name is not None:
            names.add(type_name)
    return names


def direct_nested_type_declarations(body: JavaNode) -> Iterable[JavaNode]:
    return (child for child in body.named_children if child.type in TYPE_DECLARATION_NODES)


def iter_type_declarations(node: JavaNode) -> Iterable[JavaNode]:
    if node.type not in TYPE_DECLARATION_NODES:
        return
    yield node
    body = node.child_by_field("body")
    if body is None:
        return
    for child in direct_nested_type_declarations(body):
        yield from iter_type_declarations(child)


def iter_class_declarations(node: JavaNode) -> Iterable[JavaNode]:
    if node.type != "class_declaration":
        return
    yield node
    body = node.child_by_field("body")
    if body is None:
        return
    for child in direct_nested_type_declarations(body):
        yield from iter_class_declarations(child)


def nested_type_names_using_qualified_this(body: JavaNode | None) -> set[str]:
    if body is None:
        return set()
    names: set[str] = set()
    for child in body.named_children:
        if child.type != "class_declaration":
            continue
        type_name = type_name_of(node=child)
        if type_name is not None and uses_qualified_this(child):
            names.add(type_name)
    return names


def type_name_of(*, node: JavaNode) -> str | None:
    name_node = node.child_by_field("name")
    if name_node is None:
        return None
    return translate_class_name(name_node.text)


def uses_qualified_this(node: JavaNode) -> bool:
    if node.type == "field_access":
        children = node.named_children
        if (
            len(children) == 2
            and children[0].type
            in {"identifier", "type_identifier", "scoped_identifier", "scoped_type_identifier"}
            and children[1].type == "this"
        ):
            return True
    return any(uses_qualified_this(child) for child in node.named_children)


def references_enclosing_instance_fields(
    node: JavaNode,
    enclosing_fields: set[str],
    *,
    exclude_fields: set[str] | None = None,
) -> bool:
    """Return True when a class body references outer-instance fields by simple name."""
    if not enclosing_fields:
        return False
    excluded = exclude_fields or set()
    candidate_fields = enclosing_fields - excluded
    if not candidate_fields:
        return False

    class_scope_names = _direct_field_declaration_names(node)

    def has_simple_reference(current: JavaNode, declared_names: set[str]) -> bool:
        if current.type in {"method_declaration", "constructor_declaration"}:
            method_names = declared_names | _local_declaration_names(current)
            name_node = current.child_by_field("name")
            skipped = {node_key(name_node)} if name_node is not None else set()
            return any(
                has_simple_reference(child, method_names)
                for child in current.named_children
                if node_key(child) not in skipped
            )
        if current.type == "field_access":
            return any(
                has_simple_reference(child, declared_names) for child in current.named_children[:-1]
            )
        if current.type == "method_invocation":
            name_node = current.child_by_field("name")
            skipped = {node_key(name_node)} if name_node is not None else set()
            return any(
                has_simple_reference(child, declared_names)
                for child in current.named_children
                if node_key(child) not in skipped
            )
        if current.type in {
            "field_declaration",
            "variable_declarator",
            "formal_parameter",
            "catch_formal_parameter",
        }:
            name_node = current.child_by_field("name")
            skipped = {node_key(name_node)} if name_node is not None else set()
            return any(
                has_simple_reference(child, declared_names)
                for child in current.named_children
                if node_key(child) not in skipped
            )
        if current.type == "identifier":
            return current.text in candidate_fields and current.text not in declared_names
        return any(has_simple_reference(child, declared_names) for child in current.named_children)

    return has_simple_reference(node, class_scope_names)


def _direct_field_declaration_names(node: JavaNode) -> set[str]:
    names: set[str] = set()
    for member in node.named_children:
        if member.type != "field_declaration":
            continue
        for child in member.walk():
            if child.type == "variable_declarator":
                name_node = child.child_by_field("name")
                if name_node is not None:
                    names.add(name_node.text)
    return names


def _local_declaration_names(node: JavaNode) -> set[str]:
    names: set[str] = set()
    for child in node.walk():
        if child.type in {"variable_declarator", "formal_parameter", "catch_formal_parameter"}:
            name_node = child.child_by_field("name")
            if name_node is not None:
                names.add(name_node.text)
    return names


def _superclass_type_node(superclass: JavaNode) -> JavaNode | None:
    """Return the type-name node of an ``extends`` clause.

    The superclass may be a bare ``type_identifier``/``scoped_type_identifier`` or a
    ``generic_type`` wrapper such as ``Pair<L, R>``. In the generic case the bare name
    lives one level down, so descend into it.
    """
    type_node = first_child_by_type(superclass, "type_identifier", "scoped_type_identifier")
    if type_node is not None:
        return type_node
    generic = first_child_by_type(superclass, "generic_type")
    if generic is not None:
        return first_child_by_type(generic, "type_identifier", "scoped_type_identifier")
    return None


def base_suffix(
    node: JavaNode,
    diagnostics: TranslationDiagnostics | None = None,
    *,
    resolver: NameResolver | None = None,
    scope: NameScope | None = None,
    extra_bases: list[str] | None = None,
) -> str:
    bases: list[str] = []

    def add_base(base: str) -> None:
        if base not in bases:
            bases.append(base)

    superclass = node.child_by_field("superclass")
    if superclass is not None:
        type_node = _superclass_type_node(superclass)
        if type_node is not None:
            add_base(_superclass_binding(type_node.text, diagnostics, resolver, scope))
    for base in extra_bases or []:
        add_base(base)
    if "abstract" in _modifiers(node):
        add_base("ABC")
    if not bases:
        return ""
    return f"({', '.join(bases)})"


def _superclass_binding(
    raw_name: str,
    diagnostics: TranslationDiagnostics | None,
    resolver: NameResolver | None,
    scope: NameScope | None,
) -> str:
    """Resolve the Python base-class name and request its import if needed.

    Reuses the deterministic type-reference resolution in
    :class:`~j2py.translate.name_resolution.NameResolver` (ADR 0016): an explicit Java
    import or configured import-map binding wins, then a same-package sibling import,
    falling back to a default-package module import. A superclass declared in the same
    compilation unit (and therefore the same Python module) needs no import. The
    ``translate_class_name`` fallback keeps a class name when no binding source resolves.
    """
    simple = raw_name.rsplit(".", 1)[-1]
    if resolver is None or scope is None:
        return translate_class_name(simple)
    py_name = translate_class_name(simple)
    # A superclass declared in the same compilation unit shares the Python module, so it
    # needs no import. Check this before the resolver, whose same-package fallback would
    # otherwise emit a self-referential cross-module import.
    if py_name in resolver.bindings.compilation_unit_types:
        return py_name
    resolved = resolver.resolve_identifier(simple, scope)
    if not resolved.is_type_reference:
        return translate_class_name(simple)
    if diagnostics is not None and resolved.import_line:
        diagnostics.imports.need_line(resolved.import_line)
    return resolved.python_name


STATIC_INSTANCE_STATIC_SUFFIX = "_static"


def _member_java_parameter_count(member: JavaNode) -> int:
    params_node = member.child_by_field("parameters")
    if params_node is None:
        return 0
    return sum(1 for child in params_node.named_children if child.type == "formal_parameter")


def _member_translated_python_name(member: JavaNode, cfg: TranslationConfig) -> str:
    return translate_method_name(raw_member_name(member), snake_case=cfg.snake_case_methods)


def static_instance_collision_python_names(
    members: Iterable[JavaNode],
    cfg: TranslationConfig,
) -> frozenset[str]:
    """Python names shared by both static and instance Java overload members."""
    grouped: dict[str, list[JavaNode]] = {}
    for member in members:
        if member.type != "method_declaration":
            continue
        name = _member_translated_python_name(member, cfg)
        grouped.setdefault(name, []).append(member)
    collisions: set[str] = set()
    for name, group in grouped.items():
        if len(group) < 2:
            continue
        has_static = any("static" in _modifiers(item) for item in group)
        has_instance = any("static" not in _modifiers(item) for item in group)
        if has_static and has_instance:
            collisions.add(name)
    return frozenset(collisions)


def static_instance_collision_static_python_name(canonical_name: str) -> str:
    """Rename static overload members when an instance overload shares the name."""
    return f"{canonical_name}{STATIC_INSTANCE_STATIC_SUFFIX}"


def static_instance_collision_static_aliases(
    members: Iterable[JavaNode],
    cfg: TranslationConfig,
) -> dict[str, str]:
    """Map canonical Python method names to emitted static overload names."""
    return {
        name: static_instance_collision_static_python_name(name)
        for name in static_instance_collision_python_names(members, cfg)
    }


def static_instance_collision_zero_arg_names(
    members: Iterable[JavaNode],
    cfg: TranslationConfig,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return collision names with a zero-parameter overload on each side."""
    grouped: dict[str, list[JavaNode]] = {}
    for member in members:
        if member.type != "method_declaration":
            continue
        name = _member_translated_python_name(member, cfg)
        grouped.setdefault(name, []).append(member)

    instance_zero: set[str] = set()
    static_zero: set[str] = set()
    for name, group in grouped.items():
        if len(group) < 2:
            continue
        static_members = [item for item in group if "static" in _modifiers(item)]
        instance_members = [item for item in group if "static" not in _modifiers(item)]
        if not static_members or not instance_members:
            continue
        if any(_member_java_parameter_count(item) == 0 for item in static_members):
            static_zero.add(name)
        if any(_member_java_parameter_count(item) == 0 for item in instance_members):
            instance_zero.add(name)
    return frozenset(instance_zero), frozenset(static_zero)


def member_method_names(members: Iterable[JavaNode], cfg: TranslationConfig) -> set[str]:
    return {
        translate_method_name(raw_member_name(member), snake_case=cfg.snake_case_methods)
        for member in members
    }


def member_static_method_names(members: Iterable[JavaNode], cfg: TranslationConfig) -> set[str]:
    collisions = static_instance_collision_python_names(members, cfg)
    names: set[str] = set()
    for member in members:
        if member.type != "method_declaration" or "static" not in _modifiers(member):
            continue
        py_name = _member_translated_python_name(member, cfg)
        if py_name in collisions:
            names.add(static_instance_collision_static_python_name(py_name))
        else:
            names.add(py_name)
    return names


def _method_and_constructor_members(body: JavaNode | None) -> list[JavaNode]:
    if body is None:
        return []
    return [
        child
        for child in body.named_children
        if child.type in {"constructor_declaration", "method_declaration"}
    ]


def collect_file_class_static_methods(
    root: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, set[str]]:
    """Map translated class name to static method names declared in that class."""
    result: dict[str, set[str]] = {}

    for child in root.named_children:
        for node in iter_class_declarations(child):
            name_node = node.child_by_field("name")
            if name_node is None:
                continue
            py_name = translate_class_name(name_node.text)
            body = node.child_by_field("body")
            members = _method_and_constructor_members(body)
            result[py_name] = member_static_method_names(members, cfg)
    return result


def collect_file_class_static_instance_aliases(
    root: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    """Map translated class name to static/instance collision rename aliases."""
    result: dict[str, dict[str, str]] = {}

    for child in root.named_children:
        for node in iter_class_declarations(child):
            name_node = node.child_by_field("name")
            if name_node is None:
                continue
            py_name = translate_class_name(name_node.text)
            body = node.child_by_field("body")
            members = _method_and_constructor_members(body)
            aliases = static_instance_collision_static_aliases(members, cfg)
            if aliases:
                result[py_name] = aliases
    return result


def collect_file_class_declarations(root: JavaNode) -> dict[str, JavaNode]:
    """Map translated class name to class declaration nodes in one compilation unit."""
    result: dict[str, JavaNode] = {}

    for child in root.named_children:
        for node in iter_class_declarations(child):
            name_node = node.child_by_field("name")
            if name_node is None:
                continue
            result[translate_class_name(name_node.text)] = node
    return result


def merge_class_static_method_indexes(
    *indexes: dict[str, set[str]],
) -> dict[str, set[str]]:
    """Merge per-class static-method indexes (later indexes override earlier ones)."""
    merged: dict[str, set[str]] = {}
    for index in indexes:
        merged.update(index)
    return merged


def merge_class_static_instance_alias_indexes(
    *indexes: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Merge per-class static/instance collision alias maps."""
    merged: dict[str, dict[str, str]] = {}
    for index in indexes:
        merged.update(index)
    return merged


def merge_class_declaration_indexes(
    *indexes: dict[str, JavaNode],
) -> dict[str, JavaNode]:
    """Merge per-class declaration nodes from multiple compilation units."""
    merged: dict[str, JavaNode] = {}
    for index in indexes:
        merged.update(index)
    return merged


def _inherited_from_file_superclasses(
    node: JavaNode,
    file_class_static_methods: dict[str, set[str]],
    file_class_static_instance_aliases: dict[str, dict[str, str]],
    file_class_declarations: dict[str, JavaNode],
) -> tuple[dict[str, str], dict[str, str]]:
    """Collect inherited static dispatch and collision aliases across ``extends``."""
    dispatch: dict[str, str] = {}
    aliases: dict[str, str] = {}
    current: JavaNode | None = node
    seen: set[str] = set()
    while current is not None:
        super_simple = superclass_simple_name(current)
        if super_simple is None:
            break
        super_py = translate_class_name(super_simple)
        if super_py in seen:
            break
        seen.add(super_py)
        for method in file_class_static_methods.get(super_py, set()):
            dispatch.setdefault(method, super_py)
        for canonical, static_name in file_class_static_instance_aliases.get(super_py, {}).items():
            aliases.setdefault(canonical, static_name)
            dispatch.setdefault(canonical, super_py)
        current = file_class_declarations.get(super_py)
    return dispatch, aliases


def superclass_simple_name(node: JavaNode) -> str | None:
    superclass = node.child_by_field("superclass")
    if superclass is None:
        return None
    type_node = _superclass_type_node(superclass)
    if type_node is None:
        return None
    return type_node.text.rsplit(".", 1)[-1]


def inherited_static_dispatch(
    node: JavaNode,
    file_class_static_methods: dict[str, set[str]],
    file_class_static_instance_aliases: dict[str, dict[str, str]],
    file_class_declarations: dict[str, JavaNode],
    cfg: TranslationConfig,
) -> dict[str, str]:
    del cfg
    dispatch, _ = _inherited_from_file_superclasses(
        node,
        file_class_static_methods,
        file_class_static_instance_aliases,
        file_class_declarations,
    )
    return dispatch


def inherited_static_instance_static_aliases(
    node: JavaNode,
    file_class_static_instance_aliases: dict[str, dict[str, str]],
    file_class_declarations: dict[str, JavaNode],
    cfg: TranslationConfig,
) -> dict[str, str]:
    del cfg
    _, aliases = _inherited_from_file_superclasses(
        node,
        {},
        file_class_static_instance_aliases,
        file_class_declarations,
    )
    return aliases


def inherited_static_instance_zero_arg_names(
    node: JavaNode,
    file_class_declarations: dict[str, JavaNode],
    cfg: TranslationConfig,
) -> tuple[frozenset[str], frozenset[str]]:
    """Collect inherited zero-argument collision metadata across ``extends``."""
    instance_zero: set[str] = set()
    static_zero: set[str] = set()
    current: JavaNode | None = node
    seen: set[str] = set()
    while current is not None:
        super_simple = superclass_simple_name(current)
        if super_simple is None:
            break
        super_py = translate_class_name(super_simple)
        if super_py in seen:
            break
        seen.add(super_py)
        parent_node = file_class_declarations.get(super_py)
        if parent_node is not None:
            body = parent_node.child_by_field("body")
            members = _method_and_constructor_members(body)
            parent_instance_zero, parent_static_zero = static_instance_collision_zero_arg_names(
                members,
                cfg,
            )
            instance_zero.update(parent_instance_zero)
            static_zero.update(parent_static_zero)
        current = parent_node
    return frozenset(instance_zero), frozenset(static_zero)


def enclosing_static_dispatch_for_nested_types(
    *,
    class_name: str,
    class_static_methods: set[str],
    enclosing_static_dispatch: dict[str, str],
) -> dict[str, str]:
    dispatch = dict(enclosing_static_dispatch)
    for method in class_static_methods:
        dispatch[method] = class_name
    return dispatch


def raw_member_name(member: JavaNode) -> str:
    if member.type == "constructor_declaration":
        return "__init__"
    name_node = member.child_by_field("name")
    return name_node.text if name_node is not None else "unknown"


def member_groups(members: list[JavaNode]) -> list[list[JavaNode]]:
    order: list[str] = []
    groups: dict[str, list[JavaNode]] = {}
    for member in members:
        name = member_python_name(member)
        if name not in groups:
            order.append(name)
            groups[name] = []
        groups[name].append(member)
    return [groups[name] for name in order]


def member_python_name(member: JavaNode) -> str:
    if member.type == "constructor_declaration":
        return "__init__"
    name_node = member.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    return translate_method_name(raw_name)


def node_key(node: JavaNode) -> _NodeKey:
    location = node.location
    return (
        location.line,
        location.column,
        location.end_line,
        location.end_column,
        node.type,
    )


def member_docstrings(body: JavaNode | None, cfg: TranslationConfig) -> dict[_NodeKey, list[str]]:
    if body is None:
        return {}
    docstrings: dict[_NodeKey, list[str]] = {}
    pending: list[str] | None = None
    for child in body.named_children:
        if is_javadoc_comment(child):
            pending = javadoc_docstring(child, cfg, indent="        ")
            continue
        if child.type in {"constructor_declaration", "method_declaration"}:
            if pending:
                docstrings[node_key(child)] = pending
            pending = None
            continue
        if not is_comment(child):
            pending = None
    return docstrings


def docstring_for_group(
    group: list[JavaNode],
    docstrings: dict[_NodeKey, list[str]],
) -> list[str] | None:
    for member in reversed(group):
        docstring = docstrings.get(node_key(member))
        if docstring:
            return docstring
    return None


def javadoc_docstring(
    node: JavaNode,
    cfg: TranslationConfig,
    *,
    indent: str,
) -> list[str] | None:
    if not cfg.emit_line_comments:
        return None
    if not cfg.emit_docstrings:
        return translate_comment(node, indent=indent)
    return translate_javadoc_docstring(node, indent=indent)
