"""Assignment, update, and embedded assignment expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.java_types import is_integral_java_type, java_type_of_value
from j2py.translate.node_utils import unwrap_parens
from j2py.translate.rules.naming import translate_field_name

_ASSIGN_OR_UPDATE = {"assignment_expression", "update_expression"}


def _next_temp_id(ctx: TranslationContext) -> int:
    ctx.temporary_counter += 1
    return ctx.temporary_counter


def _desugar_embedded_assign(node: JavaNode, ctx: TranslationContext) -> str:
    """Translate an assignment/update node that appears in expression position.

    Java permits assignments as expressions (return, condition, subscript
    index).  Python does not - walrus (:=) covers plain-= with a simple-name
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
    elif operator == "/=" and is_integral_java_type(java_type_of_value(left_node, ctx)):
        ctx.diagnostics.imports.need_idiv()
        ctx.hoisted_pre_stmts.append(f"{left} = _j2py_idiv({left}, {right})")
    else:
        ctx.hoisted_pre_stmts.append(f"{left} {operator} {right}")
    ctx.diagnostics.warn(
        node,
        reason="assignment in expression position hoisted to preceding statement; verify semantics",
    )
    return left


def _desugar_postfix_update_array_access(
    array_expr: str,
    index_node: JavaNode,
    ctx: TranslationContext,
    *,
    use_ord_index: bool = False,
) -> str | None:
    """Materialize ``array[index++]`` as a value read followed by the update."""
    temp_id = _next_temp_id(ctx)
    target_pre_stmts, target, update_stmt = _postfix_update_parts(index_node, ctx, temp_id=temp_id)
    if target is None:
        return None

    array_temp = f"_j2py_arr_{temp_id}"
    index_temp = f"_j2py_index_{temp_id}"
    value_temp = f"_j2py_value_{temp_id}"
    read_index = f"ord({index_temp})" if use_ord_index else index_temp
    ctx.hoisted_pre_stmts.append(f"{array_temp} = {array_expr}")
    ctx.hoisted_pre_stmts.extend(target_pre_stmts)
    ctx.hoisted_pre_stmts.append(f"{index_temp} = {target}")
    ctx.hoisted_pre_stmts.append(f"{value_temp} = {array_temp}[{read_index}]")
    ctx.hoisted_pre_stmts.append(update_stmt)
    return value_temp


def _postfix_update_parts(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    temp_id: int,
) -> tuple[list[str], str | None, str]:
    children = node.children
    named_children = node.named_children
    if len(children) < 2 or not named_children:
        return [], None, ""
    operator = next((child.text for child in children if child.text in {"++", "--"}), None)
    if operator is None or children[0].text in {"++", "--"}:
        return [], None, ""
    target_node = named_children[0]
    op_symbol = "+" if operator == "++" else "-"
    if target_node.type == "field_access":
        target_children = target_node.named_children
        if len(target_children) >= 2:
            receiver = translate_expression(target_children[0], ctx)
            field = translate_field_name(
                target_children[-1].text,
                snake_case=ctx.cfg.snake_case_fields,
            )
            receiver_temp = f"_j2py_target_{temp_id}"
            target = f"{receiver_temp}.{field}"
            return [f"{receiver_temp} = {receiver}"], target, f"{target} {op_symbol}= 1"
    target = translate_expression(target_node, ctx)
    return [], target, f"{target} {op_symbol}= 1"


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
    # i++ / i--: value is old value.  Semantically approximate: we hoist
    # the mutation before the expression and adjust the returned value.
    ctx.diagnostics.warn(
        node,
        reason=("post-increment/decrement in expression position desugared approximately; verify"),
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
            field = translate_field_name("length", snake_case=ctx.cfg.snake_case_fields)
            return f"{target}.{field}"
    if node.type == "array_access":
        children = node.named_children
        if len(children) == 2:
            array_expr = translate_expression(children[0], ctx)
            index_inner = unwrap_parens(children[1])
            if index_inner.type in _ASSIGN_OR_UPDATE:
                index_expr = _desugar_embedded_assign(index_inner, ctx)
            else:
                index_expr = translate_expression(children[1], ctx)
            return f"{array_expr}[{index_expr}]"
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
            from j2py.translate.expr_binary import _translate_unsigned_right_shift_assign

            return _translate_unsigned_right_shift_assign(node, left_node, right_node, ctx)
        if operator == "/=" and is_integral_java_type(java_type_of_value(left_node, ctx)):
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
