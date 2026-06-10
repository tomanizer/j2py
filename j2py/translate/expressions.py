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
from j2py.translate.rules.types import translate_type


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

    if node.type in {"type_identifier", "scoped_type_identifier"}:
        return translate_class_name(node.text)

    if node.type == "this":
        return "self"

    if node.type == "field_access":
        return _translate_field_access(node, ctx)

    if node.type == "array_access":
        return _translate_array_access(node, ctx)

    if node.type == "array_initializer":
        return _translate_array_initializer(node, ctx)

    if node.type == "array_creation_expression":
        return _translate_array_creation(node, ctx)

    if node.type == "class_literal":
        return _translate_class_literal(node, ctx)

    if node.type == "assignment_expression":
        children = node.children
        if len(children) >= 3:
            left_node = children[0]
            operator = children[1].text
            right_node = children[-1]
            if operator not in {"=", "+=", "-=", "*=", "/=", "%="}:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=f"unsupported assignment operator {operator}",
                )
                return f"__j2py_todo__({node.text!r})"
            left = translate_expression(left_node, ctx)
            right = translate_expression(right_node, ctx)
            return f"{left} {operator} {right}"

    if node.type == "update_expression":
        return _translate_update_expression(node, ctx)

    if node.type == "method_invocation":
        return _translate_method_invocation(node, ctx)

    if node.type == "lambda_expression":
        return _translate_lambda_expression(node, ctx)

    if node.type == "method_reference":
        return _translate_method_reference(node, ctx)

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

    if node.type == "ternary_expression":
        return _translate_ternary_expression(node, ctx)

    if node.type == "switch_expression":
        return _translate_switch_expression(node, ctx)

    if node.type == "binary_expression":
        f_string = _translate_string_concat(node, ctx)
        if f_string is not None:
            return f_string
        children = node.children
        if len(children) >= 3:
            operator_text = children[1].text
            if operator_text == "/":
                return _translate_division(node, children[0], children[2], ctx)
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
            return (
                f"{translate_expression(children[0], ctx)} "
                f"{binary_operator} "
                f"{translate_expression(children[2], ctx)}"
            )

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported expression {node.type}")
    return f"__j2py_todo__({node.text!r})"


def _translate_identifier(raw_name: str, ctx: TranslationContext) -> str:
    if raw_name in ctx.expression_aliases:
        return ctx.expression_aliases[raw_name]
    py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
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
    field_name = translate_field_name(
        children[-1].text,
        snake_case=ctx.cfg.snake_case_fields,
    )
    if children[-1].text == "length":
        return f"len({target})"
    return f"{target}.{field_name}"


def _translate_array_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) != 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed array access")
        return f"__j2py_todo__({node.text!r})"
    return f"{translate_expression(children[0], ctx)}[{translate_expression(children[1], ctx)}]"


def _translate_array_initializer(node: JavaNode, ctx: TranslationContext) -> str:
    return f"[{', '.join(translate_expression(child, ctx) for child in node.named_children)}]"


def _translate_array_creation(node: JavaNode, ctx: TranslationContext) -> str:
    initializer = first_child_by_type(node, "array_initializer")
    if initializer is not None:
        return translate_expression(initializer, ctx)
    ctx.diagnostics.record(
        node,
        supported=False,
        reason="array creation without initializer requires size handling",
    )
    return f"__j2py_todo__({node.text!r})"


def _translate_class_literal(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if not children:
        ctx.diagnostics.record(node, supported=False, reason="malformed class literal")
        return f"__j2py_todo__({node.text!r})"
    return translate_expression(children[0], ctx)


def _translate_method_invocation(node: JavaNode, ctx: TranslationContext) -> str:
    stream_pipeline = _translate_stream_pipeline(node, ctx)
    if stream_pipeline is not None:
        return stream_pipeline

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

    if method_name in {"size", "length"} and receiver and not args:
        return f"len({receiver})"

    if method_name == "isEmpty" and receiver and not args:
        return f"not {receiver}"

    if method_name == "contains" and receiver and args:
        return f"{args} in {receiver}"

    if method_name == "get" and receiver and args:
        receiver_type = _expression_py_type(receiver_nodes[0], ctx) if receiver_nodes else None
        if receiver_type is not None and _is_list_type(receiver_type):
            return f"{receiver}[{args}]"
        if receiver_type is not None and _is_dict_type(receiver_type):
            return f"{receiver}.get({args})"
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="ambiguous get invocation requires receiver collection type",
        )
        return f"{receiver}.get({args})"

    if method_name == "equals" and receiver and args:
        arg_nodes = list(args_node.named_children) if args_node is not None else []
        if len(arg_nodes) != 1:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="equals invocation with unexpected argument count",
            )
            return f"__j2py_todo__({node.text!r})"
        if arg_nodes[0].type == "null_literal":
            return f"{receiver} is None"
        return f"{receiver} == {args}"

    if method_name == "equalsIgnoreCase" and receiver and args:
        arg_nodes = list(args_node.named_children) if args_node is not None else []
        if len(arg_nodes) == 1:
            return f"{receiver}.lower() == {args}.lower()"

    if method_name == "toString" and receiver and not args:
        return f"str({receiver})"

    if method_name == "hashCode" and receiver and not args:
        return f"hash({receiver})"

    if method_name == "startsWith" and receiver and args:
        return f"{receiver}.startswith({args})"

    if method_name == "endsWith" and receiver and args:
        return f"{receiver}.endswith({args})"

    if method_name == "trim" and receiver and not args:
        return f"{receiver}.strip()"

    if method_name == "toLowerCase" and receiver and not args:
        return f"{receiver}.lower()"

    if method_name == "toUpperCase" and receiver and not args:
        return f"{receiver}.upper()"

    if method_name == "compareTo" and receiver and args:
        return f"({receiver} > {args}) - ({receiver} < {args})"

    py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
    if receiver:
        return f"{receiver}.{py_method}({args})"
    return f"{py_method}({args})"


def _translate_stream_pipeline(node: JavaNode, ctx: TranslationContext) -> str | None:
    chain = _stream_chain(node)
    if chain is None:
        return None

    source_node, operations = chain
    if not operations or operations[-1][0] not in {"collect", "toList"}:
        return None

    terminal_name, terminal_arg = operations[-1]
    if terminal_name == "collect" and not _is_collectors_to_list(terminal_arg):
        return None

    source = translate_expression(source_node, ctx)
    item_name = _stream_item_name(source, ctx)
    current_expr = item_name
    filters: list[str] = []
    for operation, arg in operations[:-1]:
        if operation == "map" and arg is not None:
            mapped = _stream_map_expression(arg, item_name, ctx)
            if mapped is None:
                return None
            current_expr = mapped
            continue
        if operation == "filter" and arg is not None:
            predicate = _stream_filter_expression(arg, current_expr, item_name, ctx)
            if predicate is None:
                return None
            filters.append(predicate)
            continue
        return None

    filter_suffix = f" if {' and '.join(filters)}" if filters else ""
    return f"[{current_expr} for {item_name} in {source}{filter_suffix}]"


def _stream_chain(node: JavaNode) -> tuple[JavaNode, list[tuple[str, JavaNode | None]]] | None:
    if node.type != "method_invocation":
        return None
    receiver = node.child_by_field("object")
    name_node = node.child_by_field("name")
    args_node = node.child_by_field("arguments") or first_child_by_type(node, "argument_list")
    if receiver is None or name_node is None:
        return None

    method_name = name_node.text
    arg = (
        args_node.named_children[0]
        if args_node is not None and args_node.named_children
        else None
    )
    if method_name == "stream":
        return receiver, []

    previous = _stream_chain(receiver)
    if previous is None:
        return None
    source, operations = previous
    return source, [*operations, (method_name, arg)]


def _is_collectors_to_list(node: JavaNode | None) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == "toList"
    )


def _stream_item_name(source: str, ctx: TranslationContext) -> str:
    base = source.rsplit(".", 1)[-1]
    if base.endswith("ies") and len(base) > 3:
        base = f"{base[:-3]}y"
    elif base.endswith("s") and len(base) > 1:
        base = base[:-1]
    return translate_field_name(base or "item", snake_case=ctx.cfg.snake_case_fields)


def _stream_map_expression(arg: JavaNode, item_name: str, ctx: TranslationContext) -> str | None:
    if arg.type == "lambda_expression":
        return _lambda_body_expression(arg, ctx, default_alias=item_name)
    if arg.type == "method_reference":
        named = arg.named_children
        if len(named) == 1 and arg.children[-1].text == "new":
            return f"{_method_reference_target(named[0], ctx)}({item_name})"
        if len(named) >= 2 and named[0].text[:1].isupper():
            method_name = translate_method_name(
                named[-1].text,
                snake_case=ctx.cfg.snake_case_methods,
            )
            return f"{item_name}.{method_name}()"
        if len(named) >= 2:
            target = _method_reference_target(named[0], ctx)
            method_name = translate_method_name(
                named[-1].text,
                snake_case=ctx.cfg.snake_case_methods,
            )
            return f"{target}.{method_name}({item_name})"
    return None


def _stream_filter_expression(
    arg: JavaNode,
    current_expr: str,
    item_name: str,
    ctx: TranslationContext,
) -> str | None:
    if arg.type == "lambda_expression":
        return _lambda_body_expression(arg, ctx, default_alias=current_expr)
    if arg.type == "method_reference":
        mapped = _stream_map_expression(arg, item_name, ctx)
        return mapped
    return None


def _lambda_body_expression(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    default_alias: str,
) -> str | None:
    params_node = node.child_by_field("parameters")
    body_node = node.child_by_field("body")
    if params_node is None or body_node is None or body_node.type == "block":
        return None
    params = _lambda_parameters(params_node, ctx)
    if len(params) != 1:
        return None

    raw_name = params[0][0]
    previous_aliases = dict(ctx.expression_aliases)
    ctx.expression_aliases[raw_name] = default_alias
    body = translate_expression(body_node, ctx)
    ctx.expression_aliases = previous_aliases
    return body


def _translate_lambda_expression(node: JavaNode, ctx: TranslationContext) -> str:
    params_node = node.child_by_field("parameters")
    body_node = node.child_by_field("body")
    if params_node is None or body_node is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed lambda expression")
        return f"__j2py_todo__({node.text!r})"

    if body_node.type == "block":
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="block lambda requires helper function",
        )
        return f"__j2py_todo__({node.text!r})"

    params = _lambda_parameters(params_node, ctx)
    previous_locals = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    for raw_name, _py_name, py_type in params:
        ctx.local_names.add(raw_name)
        if py_type is not None:
            ctx.variable_types[raw_name] = py_type
    body = translate_expression(body_node, ctx)
    ctx.local_names = previous_locals
    ctx.variable_types = previous_types

    rendered_params = ", ".join(py_name for _raw_name, py_name, _py_type in params)
    if rendered_params:
        return f"lambda {rendered_params}: {body}"
    return f"lambda: {body}"


def _lambda_parameters(
    node: JavaNode,
    ctx: TranslationContext,
) -> list[tuple[str, str, str | None]]:
    if node.type == "identifier":
        return [
            (
                node.text,
                translate_field_name(node.text, snake_case=ctx.cfg.snake_case_fields),
                None,
            ),
        ]

    params: list[tuple[str, str, str | None]] = []
    for child in node.named_children:
        if child.type == "formal_parameter":
            name_node = child.child_by_field("name")
            if name_node is None:
                continue
            type_node = child.child_by_field("type")
            params.append(
                (
                    name_node.text,
                    translate_field_name(name_node.text, snake_case=ctx.cfg.snake_case_fields),
                    translate_type(type_node.text, ctx.cfg) if type_node is not None else None,
                ),
            )
        elif child.type == "identifier":
            params.append(
                (
                    child.text,
                    translate_field_name(child.text, snake_case=ctx.cfg.snake_case_fields),
                    None,
                ),
            )
    return params


def _translate_method_reference(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named = node.named_children
    if len(children) < 3 or not named:
        ctx.diagnostics.record(node, supported=False, reason="malformed method reference")
        return f"__j2py_todo__({node.text!r})"

    target = _method_reference_target(named[0], ctx)
    if children[-1].text == "new":
        if named[0].type == "array_type":
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="array constructor method reference requires collection conversion",
            )
            return f"__j2py_todo__({node.text!r})"
        return target

    method_node = named[-1]
    if method_node == named[0]:
        ctx.diagnostics.record(node, supported=False, reason="malformed method reference")
        return f"__j2py_todo__({node.text!r})"
    method_name = translate_method_name(method_node.text, snake_case=ctx.cfg.snake_case_methods)
    return f"{target}.{method_name}"


def _method_reference_target(node: JavaNode, ctx: TranslationContext) -> str:
    if node.text[:1].isupper():
        return translate_class_name(node.text)
    return translate_expression(node, ctx)


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

    operator = children[-1].text
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
    }
    return operators.get(operator)


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
        # Java int division truncates; make that visible while still lowering confidence.
        ctx.diagnostics.record(
            node,
            supported=False,
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
    value = ast.literal_eval(node.text)
    return str(value)


def _expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    if node.type == "decimal_integer_literal":
        return "int"
    if node.type == "decimal_floating_point_literal":
        return "float"
    if node.type == "identifier":
        return ctx.variable_types.get(node.text) or ctx.class_field_types.get(node.text)
    if node.type == "field_access":
        children = node.named_children
        if len(children) == 2 and children[0].type == "this":
            return ctx.class_field_types.get(children[1].text)
    if node.type == "parenthesized_expression" and len(node.named_children) == 1:
        return _expression_py_type(node.named_children[0], ctx)
    return None


def _is_list_type(py_type: str) -> bool:
    return py_type == "list" or py_type.startswith("list[")


def _is_dict_type(py_type: str) -> bool:
    return py_type == "dict" or py_type.startswith("dict[")
