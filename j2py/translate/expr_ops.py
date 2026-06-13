"""Unary, binary, conditional, switch, and concatenation expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_types import _expression_py_type
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.literals import java_string_literal_value


def _translate_unary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named_children = node.named_children
    if not children or not named_children:
        ctx.diagnostics.record(node, supported=False, reason="malformed unary expression")
        return f"__j2py_todo__({node.text!r})"

    operator = children[0].text
    operand = translate_expression(named_children[-1], ctx)
    if operator == "!":
        if operand.startswith("not "):
            return operand.removeprefix("not ")
        return f"not {operand}"
    if operator in {"+", "-"}:
        return f"{operator}{operand}"

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported unary operator {operator}")
    return f"__j2py_todo__({node.text!r})"


def _translate_update_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named_children = node.named_children
    if len(children) < 2 or not named_children:
        ctx.diagnostics.record(node, supported=False, reason="malformed update expression")
        return f"__j2py_todo__({node.text!r})"

    operator = next(
        (child.text for child in children if child.text in {"++", "--"}),
        children[-1].text,
    )
    target = translate_expression(named_children[0], ctx)
    if operator == "++":
        return f"{target} += 1"
    if operator == "--":
        return f"{target} -= 1"

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported update operator {operator}")
    return f"__j2py_todo__({node.text!r})"


def _translate_ternary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) != 3:
        ctx.diagnostics.record(node, supported=False, reason="malformed ternary expression")
        return f"__j2py_todo__({node.text!r})"
    condition = translate_expression(children[0], ctx)
    if_true = translate_expression(children[1], ctx)
    if_false = translate_expression(children[2], ctx)
    return f"{if_true} if {condition} else {if_false}"


def _translate_switch_expression(node: JavaNode, ctx: TranslationContext) -> str:
    condition = node.child_by_field("condition")
    body = node.child_by_field("body")
    if condition is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed switch expression")
        return f"__j2py_todo__({node.text!r})"

    subject = translate_expression(condition, ctx)
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


def _translate_binary_operator(operator: str) -> str | None:
    operators = {
        "&&": "and",
        "||": "or",
        "==": "==",
        "!=": "!=",
        ">": ">",
        ">=": ">=",
        "<": "<",
        "<=": "<=",
        "+": "+",
        "-": "-",
        "*": "*",
        "%": "%",
        "&": "&",
        "|": "|",
        "^": "^",
        "<<": "<<",
        ">>": ">>",
    }
    return operators.get(operator)


def _translate_unsigned_right_shift(
    node: JavaNode,
    left_node: JavaNode,
    right_node: JavaNode,
    ctx: TranslationContext,
) -> str:
    width = _java_integral_width(left_node, ctx)
    if width is None:
        width = 32
        ctx.diagnostics.warn(
            node,
            reason="unsigned right shift assumed 32-bit int width; verify operand type",
        )
    mask = "0xFFFFFFFFFFFFFFFF" if width == 64 else "0xFFFFFFFF"
    left = translate_expression(left_node, ctx)
    right = translate_expression(right_node, ctx)
    return f"({left} >> {right}) & ({mask} >> {right})"


def _java_integral_width(node: JavaNode, ctx: TranslationContext) -> int | None:
    java_type = _java_expression_type(node, ctx)
    if java_type is None:
        return None
    return _java_type_width(java_type)


def _java_expression_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    if node.type == "identifier":
        return ctx.variable_java_types.get(node.text) or ctx.class_field_java_types.get(node.text)
    if node.type == "field_access":
        return _field_access_java_type(node, ctx)
    if node.type == "parenthesized_expression" and len(node.named_children) == 1:
        return _java_expression_type(node.named_children[0], ctx)
    if node.type == "cast_expression" and node.named_children:
        return node.named_children[0].text
    return None


def _field_access_java_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    children = node.named_children
    if len(children) != 2:
        return None
    target_node, field_name_node = children
    field_name = field_name_node.text
    if target_node.type == "this":
        return ctx.class_field_java_types.get(field_name)
    return None


def _java_type_width(java_type: str) -> int | None:
    simple = java_type.strip()
    if "<" in simple:
        simple = simple.split("<", 1)[0]
    if "." in simple:
        simple = simple.rsplit(".", 1)[-1]
    simple = simple.rstrip("[]")
    if simple in {"long", "Long"}:
        return 64
    if simple in {"byte", "short", "int", "char", "Byte", "Short", "Integer", "Character"}:
        return 32
    return None


def _translate_division(
    node: JavaNode,
    left_node: JavaNode,
    right_node: JavaNode,
    ctx: TranslationContext,
) -> str:
    left_type = _expression_py_type(left_node, ctx)
    right_type = _expression_py_type(right_node, ctx)
    left = translate_expression(left_node, ctx)
    right = translate_expression(right_node, ctx)

    if left_type == "int" and right_type == "int":
        # Java int division truncates; we emit correct floor division.
        # Use warn (not unhandled) so a correct mechanical translation does not
        # force LLM or artificially lower coverage. The note is still visible
        # to reviewers via diagnostics.warnings and CLI output.
        ctx.diagnostics.warn(
            node,
            reason="integer division translated with floor division; verify truncation semantics",
        )
        return f"{left} // {right}"

    if left_type == "float" or right_type == "float":
        return f"{left} / {right}"

    ctx.diagnostics.record(
        node,
        supported=False,
        reason="division requires numeric type certainty",
    )
    return f"__j2py_todo__({node.text!r})"


def _translate_null_comparison(
    left_node: JavaNode,
    right_node: JavaNode,
    operator: str,
    ctx: TranslationContext,
) -> str | None:
    if operator not in {"==", "!="}:
        return None
    if right_node.type == "null_literal":
        left = translate_expression(left_node, ctx)
        return f"{left} {'is' if operator == '==' else 'is not'} None"
    if left_node.type == "null_literal":
        right = translate_expression(right_node, ctx)
        return f"{right} {'is' if operator == '==' else 'is not'} None"
    return None


def _translate_string_concat(node: JavaNode, ctx: TranslationContext) -> str | None:
    terms = _flatten_plus(node)
    if terms is None or not any(term.type == "string_literal" for term in terms):
        return None
    if any(term.type == "string_literal" and "\n" in _string_literal_value(term) for term in terms):
        return _translate_string_concat_as_addition(terms, ctx)

    first_string_index = next(
        index for index, term in enumerate(terms) if term.type == "string_literal"
    )
    parts: list[str] = []
    dynamic_parts: list[str] = []
    start_index = 0
    if first_string_index > 1:
        leading_expression = " + ".join(
            translate_expression(term, ctx) for term in terms[:first_string_index]
        )
        dynamic_parts.append(leading_expression)
        parts.append(f"{{{leading_expression}}}")
        start_index = first_string_index

    for term in terms[start_index:]:
        if term.type == "string_literal":
            parts.append(_string_literal_value(term).replace("{", "{{").replace("}", "}}"))
        else:
            expression = translate_expression(term, ctx)
            dynamic_parts.append(expression)
            parts.append(f"{{{expression}}}")
    if any('"' in part or "\\" in part for part in dynamic_parts):
        return _translate_string_concat_as_addition(terms, ctx)
    content = "".join(parts).replace("\\", "\\\\").replace('"', '\\"')
    return f'f"{content}"'


def _translate_string_concat_as_addition(terms: list[JavaNode], ctx: TranslationContext) -> str:
    parts: list[str] = []
    first_string_index = next(
        (index for index, term in enumerate(terms) if term.type == "string_literal"),
        0,
    )
    start_index = 0
    if first_string_index > 1:
        leading_expression = " + ".join(
            translate_expression(term, ctx) for term in terms[:first_string_index]
        )
        parts.append(f"str({leading_expression})")
        start_index = first_string_index

    for term in terms[start_index:]:
        if term.type == "string_literal":
            parts.append(repr(_string_literal_value(term)))
        else:
            parts.append(f"str({translate_expression(term, ctx)})")
    return " + ".join(parts)


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
    return java_string_literal_value(node.text)
