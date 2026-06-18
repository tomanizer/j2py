"""Switch expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import translate_type


def _translate_switch_expression(node: JavaNode, ctx: TranslationContext) -> str:
    condition = node.child_by_field("condition")
    body = node.child_by_field("body")
    if condition is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed switch expression")
        return f"__j2py_todo__({node.text!r})"

    subject = translate_expression(condition, ctx)
    if _switch_expression_has_pattern_labels(body):
        return _translate_pattern_switch_expression(node, body, subject, ctx)

    cases: list[tuple[list[str], str]] = []
    default: str | None = None
    for rule in body.named_children:
        if rule.type != "switch_rule":
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="colon switch expression requires statement translation",
            )
            return f"__j2py_todo__({node.text!r})"
        label = first_child_by_type(rule, "switch_label")
        value_node = _switch_rule_value_node(rule)
        if label is None or value_node is None:
            ctx.diagnostics.record(node, supported=False, reason="malformed switch rule")
            return f"__j2py_todo__({node.text!r})"
        value = _switch_rule_value(value_node, ctx)
        if value is None:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="switch rule block requires a single yield expression",
            )
            return f"__j2py_todo__({node.text!r})"
        labels = _switch_label_values(label, ctx)
        if labels:
            cases.append((labels, value))
        else:
            default = value

    if default is None:
        ctx.diagnostics.record(node, supported=False, reason="switch expression without default")
        return f"__j2py_todo__({node.text!r})"

    expression = default
    for labels, value in reversed(cases):
        expression = f"{value} if {_switch_condition(subject, labels)} else {expression}"
    return expression


def _switch_expression_has_pattern_labels(body: JavaNode) -> bool:
    for label in body.find_all("switch_label"):
        if first_child_by_type(label, "pattern", "guard") is not None:
            return True
    return False


def _translate_pattern_switch_expression(
    node: JavaNode,
    body: JavaNode,
    subject: str,
    ctx: TranslationContext,
) -> str:
    helper_name = f"_j2py_switch_{len(ctx.pending_local_helpers) + 1}"
    helper_lines = [
        "",
        "            match _j2py_subject:",
    ]
    saw_default = False
    return_types: list[str] = []
    for rule in body.named_children:
        if rule.type != "switch_rule":
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="pattern switch with colon groups requires manual translation",
            )
            return f"__j2py_todo__({node.text!r})"
        label = first_child_by_type(rule, "switch_label")
        value_node = _switch_rule_value_node(rule)
        if label is None or value_node is None:
            ctx.diagnostics.record(node, supported=False, reason="malformed pattern switch rule")
            return f"__j2py_todo__({node.text!r})"
        case_headers = _pattern_switch_case_headers(label, ctx)
        if case_headers is None:
            ctx.diagnostics.record(
                label,
                supported=False,
                reason="unsupported pattern switch label",
            )
            return f"__j2py_todo__({node.text!r})"
        if not case_headers:
            case_headers = [("case _", [])]
            saw_default = True
        value = _switch_rule_value_with_bindings(value_node, ctx, case_headers[0][1])
        if value is None:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="pattern switch rule block requires a single yield expression",
            )
            return f"__j2py_todo__({node.text!r})"
        return_types.append(_pattern_switch_value_type(value))
        for header, bindings in case_headers:
            helper_lines.append(f"                {header}:")
            rule_value = value
            if bindings != case_headers[0][1]:
                alternate_value = _switch_rule_value_with_bindings(value_node, ctx, bindings)
                if alternate_value is None:
                    ctx.diagnostics.record(
                        node,
                        supported=False,
                        reason="pattern switch rule block requires a single yield expression",
                    )
                    return f"__j2py_todo__({node.text!r})"
                rule_value = alternate_value
                return_types.append(_pattern_switch_value_type(rule_value))
            helper_lines.append(f"                    return {rule_value}")
    if not saw_default:
        ctx.diagnostics.record(node, supported=False, reason="pattern switch without default")
        return f"__j2py_todo__({node.text!r})"
    helper_lines[0] = (
        f"        def {helper_name}(_j2py_subject: object)"
        f" -> {_common_pattern_switch_return_type(return_types)}:"
    )
    ctx.pending_local_helpers.append(helper_lines)
    ctx.diagnostics.record(node, supported=True, reason="translated pattern switch expression")
    return f"{helper_name}({subject})"


def _common_pattern_switch_return_type(types: list[str]) -> str:
    concrete = {item for item in types if item != "object"}
    if len(concrete) == 1 and "object" not in types:
        return concrete.pop()
    return "object"


def _pattern_switch_value_type(value: str) -> str:
    if value.startswith(('"', "'", 'f"', "f'")):
        return "str"
    if value in {"True", "False"}:
        return "bool"
    if value == "None":
        return "None"
    if value.isdecimal() or (value.startswith("-") and value[1:].isdecimal()):
        return "int"
    return "object"


def _pattern_switch_case_headers(
    label: JavaNode,
    ctx: TranslationContext,
) -> list[tuple[str, list[tuple[str, str, str]]]] | None:
    if label.text.strip() == "default":
        return []
    guard = first_child_by_type(label, "guard")
    guard_expr = guard.named_children[0] if guard is not None and guard.named_children else None
    labels: list[tuple[str, list[tuple[str, str, str]]]] = []
    for child in label.named_children:
        if child.type == "guard":
            continue
        if child.type == "null_literal":
            labels.append(("case None", []))
            continue
        if child.type == "pattern":
            parsed = _type_pattern_case(child, ctx)
            if parsed is None:
                return None
            header, bindings = parsed
            if guard_expr is not None:
                guard_text = _translate_with_pattern_bindings(guard_expr, ctx, bindings)
                header = f"{header} if {guard_text}"
            labels.append((header, bindings))
            continue
        labels.append((f"case {translate_expression(child, ctx)}", []))
    return labels


def _type_pattern_case(
    pattern: JavaNode,
    ctx: TranslationContext,
) -> tuple[str, list[tuple[str, str, str]]] | None:
    type_pattern = first_child_by_type(pattern, "type_pattern")
    if type_pattern is None:
        return None
    children = type_pattern.named_children
    if len(children) != 2:
        return None
    type_node, name_node = children
    py_type = translate_type(type_node.text, ctx.cfg)
    py_name = translate_field_name(name_node.text, snake_case=ctx.cfg.snake_case_fields)
    binding = (name_node.text, py_name, py_type)
    return f"case {py_type}() as {py_name}", [binding]


def _switch_rule_value_with_bindings(
    value_node: JavaNode,
    ctx: TranslationContext,
    bindings: list[tuple[str, str, str]],
) -> str | None:
    return _translate_optional_switch_value(value_node, ctx, bindings)


def _translate_optional_switch_value(
    value_node: JavaNode,
    ctx: TranslationContext,
    bindings: list[tuple[str, str, str]],
) -> str | None:
    if value_node.type == "expression_statement" and value_node.named_children:
        return _translate_with_pattern_bindings(value_node.named_children[0], ctx, bindings)
    if value_node.type == "block":
        yields = [child for child in value_node.named_children if child.type == "yield_statement"]
        if len(yields) == 1 and len(yields[0].named_children) == 1:
            return _translate_with_pattern_bindings(yields[0].named_children[0], ctx, bindings)
    return None


def _translate_with_pattern_bindings(
    node: JavaNode,
    ctx: TranslationContext,
    bindings: list[tuple[str, str, str]],
) -> str:
    previous_local_names = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    previous_java_types = dict(ctx.variable_java_types)
    previous_aliases = dict(ctx.expression_aliases)
    try:
        for raw_name, py_name, py_type in bindings:
            ctx.local_names.add(raw_name)
            ctx.variable_types[raw_name] = py_type
            ctx.variable_java_types[raw_name] = py_type
            ctx.expression_aliases[raw_name] = py_name
        return translate_expression(node, ctx)
    finally:
        ctx.expression_aliases = previous_aliases
        ctx.local_names = previous_local_names
        ctx.variable_types = previous_types
        ctx.variable_java_types = previous_java_types


def _switch_rule_value_node(rule: JavaNode) -> JavaNode | None:
    children = [child for child in rule.named_children if child.type != "switch_label"]
    return children[0] if len(children) == 1 else None


def _switch_rule_value(node: JavaNode, ctx: TranslationContext) -> str | None:
    if node.type == "expression_statement" and node.named_children:
        return translate_expression(node.named_children[0], ctx)
    if node.type == "block":
        yields = [child for child in node.named_children if child.type == "yield_statement"]
        if len(yields) == 1 and len(yields[0].named_children) == 1:
            return translate_expression(yields[0].named_children[0], ctx)
    return None


def _switch_label_values(label: JavaNode, ctx: TranslationContext) -> list[str]:
    return [translate_expression(child, ctx) for child in label.named_children]


def _switch_condition(subject: str, labels: list[str]) -> str:
    if len(labels) == 1:
        return f"{subject} == {labels[0]}"
    return f"{subject} in ({', '.join(labels)})"
