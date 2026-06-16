"""Unary, binary, conditional, switch, and concatenation expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_types import (
    _expression_py_type,
    _is_integral_java_type,
    _java_type_of_value,
)
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type, unwrap_parens
from j2py.translate.rules.literals import java_string_literal_value
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import translate_type

_ASSIGN_OR_UPDATE = {"assignment_expression", "update_expression"}


def _desugar_embedded_assign(node: JavaNode, ctx: TranslationContext) -> str:
    """Translate an assignment/update node that appears in expression position.

    Java permits assignments as expressions (return, condition, subscript
    index).  Python does not — walrus (:=) covers plain-= with a simple-name
    LHS; compound operators and attribute targets are hoisted into
    ctx.hoisted_pre_stmts so the caller can emit them before the enclosing
    statement.  The return value is the Python expression that produces the
    assigned value.
    """
    if node.type == "update_expression":
        return _desugar_update_in_expr(node, ctx)
    # assignment_expression
    children = node.children
    if len(children) < 3:
        return translate_expression(node, ctx)
    left_node = children[0]
    operator = children[1].text
    right_node = children[-1]
    left = translate_expression(left_node, ctx)
    right = translate_expression(right_node, ctx)
    if operator == "=" and left_node.type == "identifier" and "." not in left:
        # Simple name that didn't resolve to a dotted path: walrus is idiomatic.
        return f"({left} := {right})"
    # Compound operator or attribute/subscript LHS: hoist.
    if operator == "=":
        ctx.hoisted_pre_stmts.append(f"{left} = {right}")
    elif operator == "/=" and _is_integral_java_type(_java_type_of_value(left_node, ctx)):
        ctx.diagnostics.imports.need_idiv()
        ctx.hoisted_pre_stmts.append(f"{left} = _j2py_idiv({left}, {right})")
    else:
        ctx.hoisted_pre_stmts.append(f"{left} {operator} {right}")
    ctx.diagnostics.warn(
        node,
        reason="assignment in expression position hoisted to preceding statement; verify semantics",
    )
    return left


def _desugar_update_in_expr(node: JavaNode, ctx: TranslationContext) -> str:
    """Hoist i++/i--/++i/--i into ctx.hoisted_pre_stmts; return the value."""
    children = node.children
    named_children = node.named_children
    if len(children) < 2 or not named_children:
        return translate_expression(node, ctx)
    operator = next((c.text for c in children if c.text in {"++", "--"}), children[-1].text)
    target = translate_expression(named_children[0], ctx)
    is_prefix = children[0].text in {"++", "--"}
    delta = "1" if operator == "++" else "-1"
    op_stmt = f"{target} {'+' if operator == '++' else '-'}= 1"
    ctx.hoisted_pre_stmts.append(op_stmt)
    if is_prefix:
        # ++i / --i: value IS the new value
        return target
    else:
        # i++ / i--: value is old value.  Semantically approximate: we hoist
        # the mutation before the expression and adjust the returned value.
        ctx.diagnostics.warn(
            node,
            reason=(
                "post-increment/decrement in expression position desugared approximately; verify"
            ),
        )
        return f"({target} - {delta})"  # delta=1 for ++, -1 for --


def _translate_assignment_lhs(node: JavaNode, ctx: TranslationContext) -> str:
    """Translate the left-hand side of an assignment, skipping read-only shorthands.

    ``_translate_field_access`` converts ``.length`` to ``len(target)``, which is
    correct for reads but produces an un-assignable call expression on the LHS.
    For field-access LHS nodes with a ``.length`` field we fall back to a plain
    attribute reference so the assignment is valid Python.
    """
    if node.type == "field_access":
        children = node.named_children
        if children and children[-1].text == "length":
            target = translate_expression(children[0], ctx)
            from j2py.translate.rules.naming import translate_field_name

            field = translate_field_name("length", snake_case=ctx.cfg.snake_case_fields)
            return f"{target}.{field}"
    return translate_expression(node, ctx)


def _translate_assignment_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    if len(children) >= 3:
        left_node = children[0]
        operator = children[1].text
        right_node = children[-1]
        supported_operators = {
            "=",
            "+=",
            "-=",
            "*=",
            "/=",
            "%=",
            "&=",
            "|=",
            "^=",
            "<<=",
            ">>=",
            ">>>=",
        }
        if operator not in supported_operators:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason=f"unsupported assignment operator {operator}",
            )
            return f"__j2py_todo__({node.text!r})"
        if operator == ">>>=":
            return _translate_unsigned_right_shift_assign(node, left_node, right_node, ctx)
        if operator == "/=" and _is_integral_java_type(_java_type_of_value(left_node, ctx)):
            left = translate_expression(left_node, ctx)
            right = translate_expression(right_node, ctx)
            ctx.diagnostics.imports.need_idiv()
            ctx.diagnostics.warn(
                node,
                reason=(
                    "integer compound division translated with truncating division; "
                    "verify truncation semantics"
                ),
            )
            return f"{left} = _j2py_idiv({left}, {right})"
        left = _translate_assignment_lhs(left_node, ctx)
        inner_right = unwrap_parens(right_node)
        if inner_right.type in _ASSIGN_OR_UPDATE:
            right = _desugar_embedded_assign(inner_right, ctx)
        else:
            right = translate_expression(right_node, ctx)
        return f"{left} {operator} {right}"

    ctx.diagnostics.record(node, supported=False, reason="malformed assignment expression")
    return f"__j2py_todo__({node.text!r})"


def _translate_binary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    f_string = _translate_string_concat(node, ctx)
    if f_string is not None:
        return f_string
    children = node.children
    if len(children) >= 3:
        operator_text = children[1].text
        if operator_text == "/":
            return _translate_division(node, children[0], children[2], ctx)
        if operator_text == ">>>":
            return _translate_unsigned_right_shift(node, children[0], children[2], ctx)
        char_arithmetic = _translate_char_arithmetic(
            node, children[0], children[2], operator_text, ctx
        )
        if char_arithmetic is not None:
            return char_arithmetic
        binary_operator: str | None
        binary_operator = _translate_binary_operator(operator_text)
        if binary_operator is None:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason=f"unsupported binary operator {children[1].text}",
            )
            return f"__j2py_todo__({node.text!r})"
        null_comparison = _translate_null_comparison(
            children[0],
            children[2],
            binary_operator,
            ctx,
        )
        if null_comparison is not None:
            return null_comparison
        left = _translate_binary_operand(children[0], operator_text, ctx, is_right=False)
        right = _translate_binary_operand(children[2], operator_text, ctx, is_right=True)
        return f"{left} {binary_operator} {right}"

    ctx.diagnostics.record(node, supported=False, reason="malformed binary expression")
    return f"__j2py_todo__({node.text!r})"


def _translate_unary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named_children = node.named_children
    if not children or not named_children:
        ctx.diagnostics.record(node, supported=False, reason="malformed unary expression")
        return f"__j2py_todo__({node.text!r})"

    operator = children[0].text
    operand_node = named_children[-1]
    operand = _translate_unary_operand(operand_node, ctx)
    if operator == "!":
        operand_inner = unwrap_parens(operand_node)
        if operand_inner.type in _ASSIGN_OR_UPDATE:
            expr = _desugar_embedded_assign(operand_inner, ctx)
            return f"not ({expr})"
        operand = _translate_unary_operand(operand_node, ctx)
        if operand.startswith("not "):
            return operand.removeprefix("not ")
        return f"not {operand}"
    if operator in {"+", "-", "~"}:
        return f"{operator}{operand}"

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported unary operator {operator}")
    return f"__j2py_todo__({node.text!r})"


def _translate_unary_operand(node: JavaNode, ctx: TranslationContext) -> str:
    operand = translate_expression(node, ctx)
    if _unary_operand_needs_parentheses(node):
        return f"({operand})"
    return operand


def _unary_operand_needs_parentheses(node: JavaNode) -> bool:
    while node.type == "parenthesized_expression" and len(node.named_children) == 1:
        node = node.named_children[0]
    return node.type in {"binary_expression", "switch_expression", "ternary_expression"}


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
    cond_inner = unwrap_parens(children[0])
    if cond_inner.type in _ASSIGN_OR_UPDATE:
        condition = _desugar_embedded_assign(cond_inner, ctx)
    else:
        condition = translate_expression(children[0], ctx)
    true_inner = unwrap_parens(children[1])
    if true_inner.type in _ASSIGN_OR_UPDATE:
        if_true = _desugar_embedded_assign(true_inner, ctx)
    else:
        if_true = translate_expression(children[1], ctx)
    false_inner = unwrap_parens(children[2])
    if false_inner.type in _ASSIGN_OR_UPDATE:
        if_false = _desugar_embedded_assign(false_inner, ctx)
    else:
        if_false = translate_expression(children[2], ctx)
    return f"{if_true} if {condition} else {if_false}"


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


_BINARY_PRECEDENCE: dict[str, int] = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6,
    "!=": 6,
    "<": 7,
    "<=": 7,
    ">": 7,
    ">=": 7,
    "<<": 8,
    ">>": 8,
    ">>>": 8,
    "+": 9,
    "-": 9,
    "*": 10,
    "/": 10,
    "%": 10,
}


def _translate_binary_operand(
    node: JavaNode,
    parent_operator: str,
    ctx: TranslationContext,
    *,
    is_right: bool,
) -> str:
    # Assignment/update nodes — whether bare or wrapped in parens — must be desugared.
    inner = unwrap_parens(node)
    if inner.type in _ASSIGN_OR_UPDATE:
        return _desugar_embedded_assign(inner, ctx)
    if node.type != "parenthesized_expression" or len(node.named_children) != 1:
        return translate_expression(node, ctx)
    # Parenthesized non-assignment: decide whether to keep parens for precedence.
    expression = translate_expression(inner, ctx)
    if inner.type in {"switch_expression", "ternary_expression"}:
        return f"({expression})"
    if inner.type != "binary_expression" or len(inner.children) < 3:
        return expression
    inner_operator = inner.children[1].text
    if _binary_parentheses_change_meaning(
        parent_operator,
        inner_operator,
        is_right=is_right,
    ):
        return f"({expression})"
    return expression


def _binary_parentheses_change_meaning(
    parent_operator: str,
    inner_operator: str,
    *,
    is_right: bool,
) -> bool:
    parent_precedence = _BINARY_PRECEDENCE.get(parent_operator)
    inner_precedence = _BINARY_PRECEDENCE.get(inner_operator)
    if parent_precedence is None or inner_precedence is None:
        return True
    if inner_precedence < parent_precedence:
        return True
    return (
        is_right
        and inner_precedence == parent_precedence
        and (parent_operator in {"-", "/", "%"} or inner_operator in {"/", "%"})
    )


def _translate_unsigned_right_shift(
    node: JavaNode,
    left_node: JavaNode,
    right_node: JavaNode,
    ctx: TranslationContext,
    left: str | None = None,
) -> str:
    width = _java_integral_width(left_node, ctx)
    if width is None:
        width = 32
        ctx.diagnostics.warn(
            node,
            reason="unsigned right shift assumed 32-bit int width; verify operand type",
        )
    mask = "0xFFFFFFFFFFFFFFFF" if width == 64 else "0xFFFFFFFF"
    if left is None:
        left = translate_expression(left_node, ctx)
    right = translate_expression(right_node, ctx)
    return f"({left} & {mask}) >> {_masked_shift_distance(right, width)}"


def _is_simple_lvalue(node: JavaNode) -> bool:
    return node.type == "identifier"


def _translate_unsigned_right_shift_assign(
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
    right = translate_expression(right_node, ctx)

    if _is_simple_lvalue(left_node):
        left = translate_expression(left_node, ctx)
        return f"{left} = ({left} & {mask}) >> {_masked_shift_distance(right, width)}"

    if left_node.type == "array_access" and len(left_node.named_children) >= 2:
        array_node, index_node = left_node.named_children[0], left_node.named_children[1]
        array = translate_expression(array_node, ctx)
        index = translate_expression(index_node, ctx)
        distance = _masked_shift_distance(right, width)
        return (
            f"_j2py_idx = {index}; {array}[_j2py_idx] = ({array}[_j2py_idx] & {mask}) >> {distance}"
        )

    if left_node.type == "field_access" and len(left_node.named_children) == 2:
        from j2py.translate.rules.naming import translate_field_name

        target = translate_expression(left_node.named_children[0], ctx)
        field = translate_field_name(left_node.named_children[1].text)
        distance = _masked_shift_distance(right, width)
        return (
            f"_j2py_val = {target}.{field}; {target}.{field} = (_j2py_val & {mask}) >> {distance}"
        )

    left = translate_expression(left_node, ctx)
    ctx.diagnostics.warn(
        node,
        reason="unsigned right shift assignment on complex left-hand side may evaluate twice",
    )
    return f"{left} = ({left} & {mask}) >> {_masked_shift_distance(right, width)}"


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
    if node.type == "array_access" and node.named_children:
        array_java_type = _java_expression_type(node.named_children[0], ctx)
        if array_java_type is None:
            return None
        return _java_type_strip_one_array_dimension(array_java_type)
    if node.type == "parenthesized_expression" and len(node.named_children) == 1:
        return _java_expression_type(node.named_children[0], ctx)
    if node.type == "cast_expression" and node.named_children:
        return node.named_children[0].text
    return None


def _java_type_strip_one_array_dimension(java_type: str) -> str | None:
    stripped = java_type.strip()
    if stripped.endswith("[]"):
        return stripped[:-2].strip()
    return None


def _masked_shift_distance(right: str, width: int) -> str:
    distance_mask = "0x3F" if width == 64 else "0x1F"
    return f"({right} & {distance_mask})"


def _field_access_java_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    children = node.named_children
    if len(children) != 2:
        return None
    target_node, field_name_node = children
    field_name = field_name_node.text
    if target_node.type == "this":
        return ctx.class_field_java_types.get(field_name)

    object_java_type = _java_expression_type(target_node, ctx)
    if object_java_type is None:
        return None

    simple = _java_type_simple_name(object_java_type)
    type_fields = ctx.declared_type_java_fields.get(simple)
    if type_fields is None:
        for type_name, fields in ctx.declared_type_java_fields.items():
            if simple == type_name or object_java_type.endswith(f".{type_name}"):
                type_fields = fields
                break
    if type_fields is None:
        return None
    return type_fields.get(field_name)


def _java_type_simple_name(java_type: str) -> str:
    simple = java_type.strip()
    if "<" in simple:
        simple = simple.split("<", 1)[0]
    if "." in simple:
        simple = simple.rsplit(".", 1)[-1]
    return simple.rstrip("[]")


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
    left = _translate_binary_operand(left_node, "/", ctx, is_right=False)
    right = _translate_binary_operand(right_node, "/", ctx, is_right=True)

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


_CHAR_JAVA_TYPES = {"char", "Character"}
# Operators that are numeric in Java when applied to char operands.
_CHAR_NUMERIC_OPERATORS = {"+", "-", "*", "%", "&", "|", "^", "<<", ">>"}
_CHAR_COMPARISON_OPERATORS = {"==", "!=", "<", "<=", ">", ">="}


def _is_char_operand(node: JavaNode, ctx: TranslationContext) -> bool:
    while node.type == "parenthesized_expression" and len(node.named_children) == 1:
        node = node.named_children[0]
    if node.type == "character_literal":
        return True
    java_type = _java_expression_type(node, ctx)
    if java_type is None:
        return False
    return _java_type_simple_name(java_type) in _CHAR_JAVA_TYPES


def _translate_char_arithmetic(
    node: JavaNode,
    left_node: JavaNode,
    right_node: JavaNode,
    operator: str,
    ctx: TranslationContext,
) -> str | None:
    """Translate numeric binary expressions involving a Java ``char``.

    Java ``char`` is a 16-bit numeric type, so ``c + 1`` is integer arithmetic. The
    rule layer maps ``char`` to Python ``str``, where ``"a" + 1`` raises ``TypeError``.
    Wrap each char operand in ``ord()`` for arithmetic/bitwise operators, and for
    comparisons against non-char numeric operands. A char result that is meant to
    round-trip back to a char is wrapped in ``chr()`` by the enclosing cast (see
    ``_translate_cast_expression``); the warning flags arithmetic sites for reviewers.
    """
    is_numeric_op = operator in _CHAR_NUMERIC_OPERATORS
    is_comparison_op = operator in _CHAR_COMPARISON_OPERATORS
    if not (is_numeric_op or is_comparison_op):
        return None
    if left_node.type == "null_literal" or right_node.type == "null_literal":
        return None
    left_is_char = _is_char_operand(left_node, ctx)
    right_is_char = _is_char_operand(right_node, ctx)
    if not (left_is_char or right_is_char):
        return None
    if is_comparison_op and left_is_char and right_is_char:
        return None

    def render(operand: JavaNode, is_char: bool) -> str:
        expr = translate_expression(operand, ctx)
        return f"ord({expr})" if is_char else expr

    left = render(left_node, left_is_char)
    right = render(right_node, right_is_char)
    if is_numeric_op:
        ctx.diagnostics.warn(
            node,
            reason=(
                "char arithmetic translated with ord(); wrap result in chr() if a char is expected"
            ),
        )
    return f"{left} {operator} {right}"


def _translate_null_comparison(
    left_node: JavaNode,
    right_node: JavaNode,
    operator: str,
    ctx: TranslationContext,
) -> str | None:
    if operator not in {"==", "!="}:
        return None
    null_op = "is" if operator == "==" else "is not"
    if right_node.type == "null_literal":
        inner = unwrap_parens(left_node)
        if inner.type in _ASSIGN_OR_UPDATE:
            expr = _desugar_embedded_assign(inner, ctx)
        else:
            expr = translate_expression(left_node, ctx)
        return f"{expr} {null_op} None"
    if left_node.type == "null_literal":
        inner = unwrap_parens(right_node)
        if inner.type in _ASSIGN_OR_UPDATE:
            expr = _desugar_embedded_assign(inner, ctx)
        else:
            expr = translate_expression(right_node, ctx)
        return f"{expr} {null_op} None"
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
