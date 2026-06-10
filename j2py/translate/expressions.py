"""Expression emission for the rule-based skeleton translator."""

from __future__ import annotations

import ast

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.literals import translate_literal
from j2py.translate.rules.naming import (
    translate_class_name,
    translate_field_name,
    translate_method_name,
)


def translate_expression(node: JavaNode | None, ctx: TranslationContext) -> str:
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
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=f"unsupported assignment operator {operator}",
                )
                return f"__j2py_todo__({node.text!r})"
            left = translate_expression(left_node, ctx)
            right = translate_expression(right_node, ctx)
            return f"{left} = {right}"

    if node.type == "method_invocation":
        return _translate_method_invocation(node, ctx)

    if node.type == "argument_list":
        return ", ".join(translate_expression(child, ctx) for child in node.named_children)

    if node.type == "object_creation_expression":
        return _translate_object_creation(node, ctx)

    if node.type == "parenthesized_expression":
        named_children = node.named_children
        if len(named_children) == 1:
            return translate_expression(named_children[0], ctx)

    if node.type == "unary_expression":
        return _translate_unary_expression(node, ctx)

    if node.type == "binary_expression":
        f_string = _translate_string_concat(node, ctx)
        if f_string is not None:
            return f_string
        children = node.children
        if len(children) >= 3:
            binary_operator = _translate_binary_operator(children[1].text)
            if binary_operator is None:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=f"unsupported binary operator {children[1].text}",
                )
                return f"__j2py_todo__({node.text!r})"
            return (
                f"{translate_expression(children[0], ctx)} "
                f"{binary_operator} "
                f"{translate_expression(children[2], ctx)}"
            )

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported expression {node.type}")
    return f"__j2py_todo__({node.text!r})"


def _translate_identifier(raw_name: str, ctx: TranslationContext) -> str:
    py_name = translate_field_name(raw_name)
    if (
        ctx.in_instance_method
        and raw_name in ctx.class_fields
        and raw_name not in ctx.param_names
        and raw_name not in ctx.local_names
    ):
        return f"self.{py_name}"
    return py_name


def _translate_field_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed field access")
        return node.text

    target = translate_expression(children[0], ctx)
    field_name = translate_field_name(children[-1].text)
    return f"{target}.{field_name}"


def _translate_method_invocation(node: JavaNode, ctx: TranslationContext) -> str:
    args_node = first_child_by_type(node, "argument_list")
    args = translate_expression(args_node, ctx) if args_node is not None else ""

    named = node.named_children
    if args_node is None or len(named) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed method invocation")
        return f"__j2py_todo__({node.text!r})"

    args_index = named.index(args_node)
    method_node = named[args_index - 1]
    method_name = method_node.text
    receiver_nodes = named[: args_index - 1]
    raw_receiver = receiver_nodes[0].text if receiver_nodes else ""
    receiver = translate_expression(receiver_nodes[0], ctx) if receiver_nodes else ""

    if raw_receiver == "System.out" and method_name == "println":
        return f"print({args})"

    if method_name == "add" and receiver:
        return f"{receiver}.append({args})"

    py_method = translate_method_name(method_name)
    if receiver:
        return f"{receiver}.{py_method}({args})"
    return f"{py_method}({args})"


def _translate_object_creation(node: JavaNode, ctx: TranslationContext) -> str:
    type_node = node.child_by_field("type")
    args_node = first_child_by_type(node, "argument_list")
    args = translate_expression(args_node, ctx) if args_node is not None else ""
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
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="non-empty collection constructor requires LLM completion",
        )
        return f"__j2py_todo__({node.text!r})"

    return f"{translate_class_name(base_type)}({args})"


def _translate_unary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named_children = node.named_children
    if not children or not named_children:
        ctx.diagnostics.record(node, supported=False, reason="malformed unary expression")
        return f"__j2py_todo__({node.text!r})"

    operator = children[0].text
    operand = translate_expression(named_children[-1], ctx)
    if operator == "!":
        return f"not {operand}"
    if operator in {"+", "-"}:
        return f"{operator}{operand}"

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported unary operator {operator}")
    return f"__j2py_todo__({node.text!r})"


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
        "/": "/",
        "%": "%",
    }
    return operators.get(operator)


def _translate_string_concat(node: JavaNode, ctx: TranslationContext) -> str | None:
    terms = _flatten_plus(node)
    if terms is None or not any(term.type == "string_literal" for term in terms):
        return None

    parts: list[str] = []
    for term in terms:
        if term.type == "string_literal":
            parts.append(_string_literal_value(term).replace("{", "{{").replace("}", "}}"))
        else:
            parts.append(f"{{{translate_expression(term, ctx)}}}")
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
