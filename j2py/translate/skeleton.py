"""Rule-based skeleton generator for the deterministic translation layer."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode, ParsedFile
from j2py.translate.rules.literals import translate_literal
from j2py.translate.rules.naming import (
    translate_class_name,
    translate_field_name,
    translate_method_name,
)
from j2py.translate.rules.types import translate_type


@dataclass
class _Stats:
    handled: int = 0
    total: int = 0

    def count(self, *, supported: bool) -> None:
        self.total += 1
        if supported:
            self.handled += 1

    @property
    def coverage(self) -> float:
        if self.total == 0:
            return 0.0
        return self.handled / self.total


@dataclass
class _Context:
    cfg: TranslationConfig
    stats: _Stats
    class_fields: set[str] = field(default_factory=set)
    local_names: set[str] = field(default_factory=set)
    param_names: set[str] = field(default_factory=set)
    in_instance_method: bool = False


def translate_skeleton(
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
) -> tuple[str, float]:
    """Produce a partial Python translation and a coverage estimate.

    Returns:
        (skeleton_source, coverage) where coverage is 0.0–1.0.
        Coverage < 1.0 triggers the LLM layer.
    """
    stats = _Stats()
    class_nodes = _top_level_classes(parsed.root)

    lines = ["from __future__ import annotations", "", ""]
    class_blocks: list[list[str]] = []
    for class_node in class_nodes:
        class_blocks.append(_translate_class(class_node, cfg, stats))

    for index, block in enumerate(class_blocks):
        if index:
            lines.append("")
            lines.append("")
        lines.extend(block)

    return "\n".join(lines) + "\n", stats.coverage


def _top_level_classes(root: JavaNode) -> list[JavaNode]:
    return [
        child
        for child in root.named_children
        if child.type in {"class_declaration", "interface_declaration", "enum_declaration"}
    ]


def _translate_class(node: JavaNode, cfg: TranslationConfig, stats: _Stats) -> list[str]:
    stats.count(supported=node.type == "class_declaration")

    name_node = node.child_by_field("name")
    if name_node is None:
        stats.count(supported=False)
        return ["class Unknown:", "    # TODO(j2py): class declaration without a name", "    pass"]

    class_name = translate_class_name(name_node.text)
    fields = _class_field_names(node)
    assigned_fields = _constructor_assigned_fields(node)
    body = node.child_by_field("body")
    members = (
        []
        if body is None
        else [
            child
            for child in body.named_children
            if child.type in {"constructor_declaration", "method_declaration"}
        ]
    )

    lines = [f"class {class_name}:"]
    unsupported_member_comments = _class_unsupported_member_comments(
        node,
        fields,
        assigned_fields,
        stats,
    )
    overloaded_names = _overloaded_member_names(members)

    if not members and not unsupported_member_comments:
        lines.append("    pass")
        return lines

    lines.extend(unsupported_member_comments)

    for member in members:
        lines.append("")
        ctx = _Context(cfg=cfg, stats=stats, class_fields=fields)
        overloaded_name = _member_python_name(member)
        unsupported_reason = (
            f"overloaded method {overloaded_name} requires LLM completion"
            if overloaded_name in overloaded_names
            else None
        )
        lines.extend(_translate_method(member, ctx, unsupported_reason=unsupported_reason))

    if _class_body_needs_pass(lines):
        lines.append("    pass")

    return lines


def _class_field_names(class_node: JavaNode) -> set[str]:
    body = class_node.child_by_field("body")
    if body is None:
        return set()

    names: set[str] = set()
    for child in body.named_children:
        if child.type != "field_declaration":
            continue
        for declarator in child.find_all("variable_declarator"):
            name_node = declarator.child_by_field("name")
            if name_node is not None:
                names.add(name_node.text)
    return names


def _constructor_assigned_fields(class_node: JavaNode) -> set[str]:
    body = class_node.child_by_field("body")
    if body is None:
        return set()

    assigned: set[str] = set()
    for member in body.named_children:
        if member.type != "constructor_declaration":
            continue
        constructor_body = member.child_by_field("body") or _first_child_by_type(
            member,
            "constructor_body",
        )
        if constructor_body is None:
            continue
        for assignment in constructor_body.find_all("assignment_expression"):
            children = assignment.named_children
            if not children:
                continue
            field_name = _this_field_name(children[0])
            if field_name is not None:
                assigned.add(field_name)
    return assigned


def _this_field_name(node: JavaNode) -> str | None:
    if node.type != "field_access":
        return None
    children = node.named_children
    if len(children) != 2 or children[0].type != "this":
        return None
    return children[1].text


def _class_unsupported_member_comments(
    class_node: JavaNode,
    fields: set[str],
    assigned_fields: set[str],
    stats: _Stats,
) -> list[str]:
    body = class_node.child_by_field("body")
    if body is None:
        return []

    comments: list[str] = []
    unassigned_fields = fields - assigned_fields
    for field_name in sorted(fields):
        stats.count(supported=field_name not in unassigned_fields)
        if field_name in unassigned_fields:
            comments.append(
                "    # TODO(j2py): field declaration not represented without "
                f"constructor assignment: {translate_field_name(field_name)}"
            )

    supported_members = {"field_declaration", "constructor_declaration", "method_declaration"}
    for child in body.named_children:
        if child.type in supported_members:
            continue
        stats.count(supported=False)
        comments.append(f"    # TODO(j2py): unsupported class member {child.type}")
    return comments


def _overloaded_member_names(members: list[JavaNode]) -> set[str]:
    counts: dict[str, int] = {}
    for member in members:
        name = _member_python_name(member)
        counts[name] = counts.get(name, 0) + 1
    return {name for name, count in counts.items() if count > 1}


def _member_python_name(member: JavaNode) -> str:
    if member.type == "constructor_declaration":
        return "__init__"
    name_node = member.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    return translate_method_name(raw_name)


def _translate_method(
    node: JavaNode,
    ctx: _Context,
    *,
    unsupported_reason: str | None = None,
) -> list[str]:
    supported = node.type in {"constructor_declaration", "method_declaration"}
    ctx.stats.count(supported=supported and unsupported_reason is None)

    is_constructor = node.type == "constructor_declaration"
    is_static = "static" in _modifiers(node)
    ctx.in_instance_method = not is_static

    name_node = node.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = "__init__" if is_constructor else translate_method_name(raw_name)
    return_type = "None" if is_constructor else _return_type(node, ctx.cfg)
    params = _params(node, ctx)
    if not is_static:
        params.insert(0, "self")

    lines: list[str] = []
    if unsupported_reason is not None:
        return [f"    # TODO(j2py): {unsupported_reason}", "    pass"]

    if is_static:
        lines.append("    @staticmethod")
    lines.append(f"    def {py_name}({', '.join(params)}) -> {return_type}:")

    body = node.child_by_field("body")
    if body is None:
        body = _first_child_by_type(node, "block", "constructor_body")

    body_lines = _translate_body(body, ctx, indent="        ") if body else ["        pass"]
    lines.extend(body_lines)
    return lines


def _modifiers(node: JavaNode) -> set[str]:
    modifiers: set[str] = set()
    for modifier_node in node.children_by_type("modifiers"):
        modifiers.update(modifier_node.text.split())
    return modifiers


def _return_type(node: JavaNode, cfg: TranslationConfig) -> str:
    type_node = node.child_by_field("type")
    if type_node is None:
        return "None"
    return translate_type(type_node.text, cfg)


def _params(node: JavaNode, ctx: _Context) -> list[str]:
    params_node = node.child_by_field("parameters")
    if params_node is None:
        return []

    params: list[str] = []
    for param in params_node.find_all("formal_parameter", "spread_parameter"):
        type_node = param.child_by_field("type")
        name_node = param.child_by_field("name")
        raw_name = name_node.text if name_node is not None else "_"
        py_name = translate_field_name(raw_name)
        py_type = translate_type(type_node.text if type_node is not None else "Object", ctx.cfg)
        ctx.param_names.add(raw_name)
        params.append(f"{py_name}: {py_type}")
    return params


def _translate_body(body: JavaNode, ctx: _Context, *, indent: str) -> list[str]:
    lines: list[str] = []
    for statement in body.named_children:
        lines.extend(_translate_statement(statement, ctx, indent=indent))
    if not lines:
        lines.append(f"{indent}pass")
    return lines


def _translate_statement(node: JavaNode, ctx: _Context, *, indent: str) -> list[str]:
    if node.type == "expression_statement":
        ctx.stats.count(supported=True)
        expr = node.named_children[0] if node.named_children else node
        return [f"{indent}{_translate_expression(expr, ctx)}"]

    if node.type == "return_statement":
        ctx.stats.count(supported=True)
        if not node.named_children:
            return [f"{indent}return"]
        return [f"{indent}return {_translate_expression(node.named_children[0], ctx)}"]

    if node.type == "local_variable_declaration":
        return _translate_local_variable_declaration(node, ctx, indent=indent)

    if node.type == "enhanced_for_statement":
        return _translate_enhanced_for(node, ctx, indent=indent)

    ctx.stats.count(supported=False)
    return [f"{indent}# TODO(j2py): unsupported {node.type}", f"{indent}pass"]


def _translate_local_variable_declaration(
    node: JavaNode,
    ctx: _Context,
    *,
    indent: str,
) -> list[str]:
    ctx.stats.count(supported=True)
    type_node = node.child_by_field("type")
    py_type = translate_type(type_node.text if type_node is not None else "Object", ctx.cfg)

    lines: list[str] = []
    for declarator in _direct_children_by_type(node, "variable_declarator"):
        name_node = declarator.child_by_field("name")
        if name_node is None:
            continue
        raw_name = name_node.text
        py_name = translate_field_name(raw_name)
        ctx.local_names.add(raw_name)
        value_node = declarator.child_by_field("value")
        value = _translate_expression(value_node, ctx) if value_node else "None"
        if value in {"[]", "{}", "set()"}:
            lines.append(f"{indent}{py_name}: {py_type} = {value}")
        else:
            lines.append(f"{indent}{py_name} = {value}")
    return lines


def _translate_enhanced_for(node: JavaNode, ctx: _Context, *, indent: str) -> list[str]:
    ctx.stats.count(supported=True)
    children = node.named_children
    if len(children) < 4:
        ctx.stats.count(supported=False)
        return [f"{indent}# TODO(j2py): malformed enhanced for statement", f"{indent}pass"]

    raw_name = children[1].text
    py_name = translate_field_name(raw_name)
    iterable = _translate_expression(children[2], ctx)
    body = children[3]

    previous_locals = set(ctx.local_names)
    ctx.local_names.add(raw_name)
    lines = [f"{indent}for {py_name} in {iterable}:"]
    lines.extend(_translate_body(body, ctx, indent=f"{indent}    "))
    ctx.local_names = previous_locals
    return lines


def _translate_expression(node: JavaNode | None, ctx: _Context) -> str:
    if node is None:
        return "None"

    if node.type in {
        "decimal_integer_literal",
        "decimal_floating_point_literal",
        "true",
        "false",
        "null_literal",
        "character_literal",
    }:
        return translate_literal(node.text, ctx.cfg)

    if node.type == "string_literal":
        return node.text

    if node.type == "identifier":
        return _translate_identifier(node.text, ctx)

    if node.type == "this":
        return "self"

    if node.type == "field_access":
        return _translate_field_access(node, ctx)

    if node.type == "assignment_expression":
        children = node.children
        if len(children) >= 3:
            left_node = children[0]
            operator = children[1].text
            right_node = children[-1]
            if operator != "=":
                ctx.stats.count(supported=False)
                return f"__j2py_todo__({node.text!r})"
            left = _translate_expression(left_node, ctx)
            right = _translate_expression(right_node, ctx)
            return f"{left} = {right}"

    if node.type == "method_invocation":
        return _translate_method_invocation(node, ctx)

    if node.type == "argument_list":
        return ", ".join(_translate_expression(child, ctx) for child in node.named_children)

    if node.type == "object_creation_expression":
        return _translate_object_creation(node, ctx)

    if node.type == "binary_expression":
        f_string = _translate_string_concat(node, ctx)
        if f_string is not None:
            return f_string
        children = node.children
        if len(children) >= 3:
            return (
                f"{_translate_expression(children[0], ctx)} "
                f"{children[1].text} "
                f"{_translate_expression(children[2], ctx)}"
            )

    ctx.stats.count(supported=False)
    return f"__j2py_todo__({node.text!r})"


def _translate_identifier(raw_name: str, ctx: _Context) -> str:
    py_name = translate_field_name(raw_name)
    if (
        ctx.in_instance_method
        and raw_name in ctx.class_fields
        and raw_name not in ctx.param_names
        and raw_name not in ctx.local_names
    ):
        return f"self.{py_name}"
    return py_name


def _translate_field_access(node: JavaNode, ctx: _Context) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.stats.count(supported=False)
        return node.text

    target = _translate_expression(children[0], ctx)
    field_name = translate_field_name(children[-1].text)
    return f"{target}.{field_name}"


def _translate_method_invocation(node: JavaNode, ctx: _Context) -> str:
    args_node = _first_child_by_type(node, "argument_list")
    args = _translate_expression(args_node, ctx) if args_node is not None else ""

    named = node.named_children
    if args_node is None or len(named) < 2:
        ctx.stats.count(supported=False)
        return f"__j2py_todo__({node.text!r})"

    args_index = named.index(args_node)
    method_node = named[args_index - 1]
    method_name = method_node.text
    receiver_nodes = named[: args_index - 1]
    raw_receiver = receiver_nodes[0].text if receiver_nodes else ""
    receiver = _translate_expression(receiver_nodes[0], ctx) if receiver_nodes else ""

    if raw_receiver == "System.out" and method_name == "println":
        return f"print({args})"

    if method_name == "add" and receiver:
        return f"{receiver}.append({args})"

    py_method = translate_method_name(method_name)
    if receiver:
        return f"{receiver}.{py_method}({args})"
    return f"{py_method}({args})"


def _translate_object_creation(node: JavaNode, ctx: _Context) -> str:
    type_node = node.child_by_field("type")
    args_node = _first_child_by_type(node, "argument_list")
    args = _translate_expression(args_node, ctx) if args_node is not None else ""
    raw_type = type_node.text if type_node is not None else "object"
    base_type = raw_type.split("<", 1)[0]

    collection_literals = {
        "ArrayList": "[]",
        "LinkedList": "[]",
        "Vector": "[]",
        "HashMap": "{}",
        "LinkedHashMap": "{}",
        "TreeMap": "{}",
        "Hashtable": "{}",
        "HashSet": "set()",
        "LinkedHashSet": "set()",
        "TreeSet": "set()",
    }
    if base_type in collection_literals:
        if not args:
            return collection_literals[base_type]
        ctx.stats.count(supported=False)
        return f"__j2py_todo__({node.text!r})"

    return f"{translate_class_name(base_type)}({args})"


def _translate_string_concat(node: JavaNode, ctx: _Context) -> str | None:
    terms = _flatten_plus(node)
    if terms is None or not any(term.type == "string_literal" for term in terms):
        return None

    parts: list[str] = []
    for term in terms:
        if term.type == "string_literal":
            parts.append(_string_literal_value(term).replace("{", "{{").replace("}", "}}"))
        else:
            parts.append(f"{{{_translate_expression(term, ctx)}}}")
    content = "".join(parts).replace("\\", "\\\\").replace('"', '\\"')
    return f'f"{content}"'


def _flatten_plus(node: JavaNode) -> list[JavaNode] | None:
    if node.type != "binary_expression":
        return [node]

    children = node.children
    if len(children) != 3 or children[1].text != "+":
        return None

    left = _flatten_plus(children[0])
    right = _flatten_plus(children[2])
    if left is None or right is None:
        return None
    return left + right


def _string_literal_value(node: JavaNode) -> str:
    value = ast.literal_eval(node.text)
    return str(value)


def _first_child_by_type(node: JavaNode, *types: str) -> JavaNode | None:
    for child in node.named_children:
        if child.type in types:
            return child
    return None


def _direct_children_by_type(node: JavaNode, *types: str) -> list[JavaNode]:
    return [child for child in node.named_children if child.type in types]


def _class_body_needs_pass(lines: list[str]) -> bool:
    class_body_lines = lines[1:]
    if not class_body_lines:
        return True
    return all(not line.strip() or line.lstrip().startswith("#") for line in class_body_lines)
