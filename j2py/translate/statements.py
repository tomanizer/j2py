"""Statement emission for the rule-based skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import direct_children_by_type, first_child_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import translate_type

TYPE_DECLARATION_NODES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}

INSTANCE_LOCK_ATTR = "_j2py_lock"


def lock_expression_is_this(lock_node: JavaNode) -> bool:
    """Return True when a synchronized lock expression is Java ``this``."""
    if lock_node.type == "this":
        return True
    if lock_node.type == "parenthesized_expression":
        inner = first_child_by_type(lock_node, "this")
        return inner is not None
    return lock_node.text.strip() in {"this", "(this)"}


def class_uses_synchronized_this(class_node: JavaNode) -> bool:
    """Return True when the class body contains ``synchronized (this)``."""
    body = class_node.child_by_field("body")
    if body is None:
        return False
    for sync in body.find_all("synchronized_statement"):
        lock = first_child_by_type(sync, "parenthesized_expression")
        if lock is not None and lock_expression_is_this(lock):
            return True
    return False


def instance_lock_init_line(*, indent: str = "        ") -> str:
    return f"{indent}self.{INSTANCE_LOCK_ATTR} = threading.Lock()"


def translate_body(body: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    lines: list[str] = []
    for statement in body.named_children:
        lines.extend(translate_statement(statement, ctx, indent=indent))
    if not lines:
        lines.append(f"{indent}pass")
    return lines


def translate_statement(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    if is_comment(node):
        ctx.diagnostics.warn(node, reason="preserved comment")
        if not ctx.cfg.emit_line_comments:
            return []
        return translate_comment(node, indent=indent)

    if node.type == "expression_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated expression statement")
        expr = node.named_children[0] if node.named_children else node
        return [f"{indent}{translate_expression(expr, ctx)}"]

    if node.type == "return_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated return statement")
        if not node.named_children:
            return [f"{indent}return"]
        return [f"{indent}return {translate_expression(node.named_children[0], ctx)}"]

    if node.type == "local_variable_declaration":
        return _translate_local_variable_declaration(node, ctx, indent=indent)

    if node.type == "enhanced_for_statement":
        return _translate_enhanced_for(node, ctx, indent=indent)

    if node.type == "if_statement":
        return _translate_if(node, ctx, indent=indent)

    if node.type == "for_statement":
        return _translate_for(node, ctx, indent=indent)

    if node.type == "while_statement":
        return _translate_while(node, ctx, indent=indent)

    if node.type == "do_statement":
        return _translate_do_while(node, ctx, indent=indent)

    if node.type == "try_statement":
        return _translate_try(node, ctx, indent=indent)

    if node.type == "try_with_resources_statement":
        return _translate_try_with_resources(node, ctx, indent=indent)

    if node.type == "synchronized_statement":
        return _translate_synchronized(node, ctx, indent=indent)

    if node.type == "switch_expression":
        # In tree-sitter-java the node type for both traditional colon switch
        # *statements* and arrow switch *expressions* is "switch_expression".
        # When it appears directly as a block child (not wrapped in
        # expression_statement), it is the statement form and must be translated
        # with the control-flow version (_translate_switch builds if/elif chains
        # or the fallthrough diagnostic). Value-producing arrow switches used in
        # expression position (or as expression_statement) are handled via
        # translate_expression -> _translate_switch_expression.
        return _translate_switch(node, ctx, indent=indent)

    if node.type == "explicit_constructor_invocation":
        return _translate_explicit_constructor_invocation(node, ctx, indent=indent)

    if node.type == "throw_statement":
        return _translate_throw(node, ctx, indent=indent)

    if node.type == "break_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated break statement")
        return [f"{indent}break"]

    if node.type == "continue_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated continue statement")
        return [f"{indent}continue"]

    if node.type in TYPE_DECLARATION_NODES:
        from j2py.translate.classes import translate_class

        return [
            f"{indent}{line}" if line else line
            for line in translate_class(node, ctx.cfg, ctx.diagnostics)
        ]

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported statement {node.type}")
    return [f"{indent}# TODO(j2py): unsupported {node.type}", f"{indent}pass"]


def _translate_local_variable_declaration(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    ctx.diagnostics.record(
        node,
        supported=True,
        reason="translated local variable declaration",
    )
    type_node = node.child_by_field("type")
    py_type = translate_type(type_node.text if type_node is not None else "Object", ctx.cfg)

    lines: list[str] = []
    for declarator in direct_children_by_type(node, "variable_declarator"):
        name_node = declarator.child_by_field("name")
        if name_node is None:
            continue
        raw_name = name_node.text
        py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
        ctx.local_names.add(raw_name)
        ctx.variable_types[raw_name] = py_type
        value_node = declarator.child_by_field("value")
        value = translate_expression(value_node, ctx) if value_node else "None"
        if not ctx.cfg.emit_type_hints:
            lines.append(f"{indent}{py_name} = {value}")
        elif value in {"[]", "{}", "set()"}:
            lines.append(f"{indent}{py_name}: {py_type} = {value}")
        else:
            lines.append(f"{indent}{py_name} = {value}")
    return lines


def _translate_enhanced_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated enhanced for statement")
    children = node.named_children
    if len(children) < 4:
        ctx.diagnostics.record(node, supported=False, reason="malformed enhanced for statement")
        return [f"{indent}# TODO(j2py): malformed enhanced for statement", f"{indent}pass"]

    raw_name = children[1].text
    py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
    iterable = translate_expression(children[2], ctx)
    body = children[3]

    previous_locals = set(ctx.local_names)
    ctx.local_names.add(raw_name)
    lines = [f"{indent}for {py_name} in {iterable}:"]
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    ctx.local_names = previous_locals
    return lines


def _translate_if(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
    keyword: str = "if",
) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated if statement")
    condition = node.child_by_field("condition")
    consequence = node.child_by_field("consequence")
    alternative = node.child_by_field("alternative")

    previous_bindings = ctx.pattern_bindings
    ctx.pattern_bindings = []
    try:
        condition_text = translate_expression(condition, ctx)
        pattern_bindings = ctx.pattern_bindings
    finally:
        ctx.pattern_bindings = previous_bindings

    lines = [f"{indent}{keyword} {condition_text}:"]
    if consequence is None:
        ctx.diagnostics.record(node, supported=False, reason="if statement without a body")
        lines.append(f"{indent}    pass")
    else:
        previous_locals = set(ctx.local_names)
        previous_types = dict(ctx.variable_types)
        for binding in pattern_bindings:
            ctx.local_names.add(binding.raw_name)
            ctx.variable_types[binding.raw_name] = binding.py_type
            lines.append(f"{indent}    {binding.py_name} = {binding.source}")
        try:
            lines.extend(translate_body(consequence, ctx, indent=f"{indent}    "))
        finally:
            ctx.local_names = previous_locals
            ctx.variable_types = previous_types

    if alternative is None:
        return lines

    if alternative.type == "if_statement":
        lines.extend(_translate_if(alternative, ctx, indent=indent, keyword="elif"))
        return lines

    lines.append(f"{indent}else:")
    lines.extend(translate_body(alternative, ctx, indent=f"{indent}    "))
    return lines


def _translate_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated for statement")
    children = node.named_children
    if len(children) < 4:
        ctx.diagnostics.record(node, supported=False, reason="malformed for statement")
        return [f"{indent}# TODO(j2py): malformed for statement", f"{indent}pass"]

    initializer, condition, update, body = children[0], children[1], children[2], children[3]
    range_loop = _range_loop_parts(initializer, condition, update, ctx)
    if range_loop is not None:
        raw_name, py_name, start, stop = range_loop
        previous_locals = set(ctx.local_names)
        ctx.local_names.add(raw_name)
        lines = [f"{indent}for {py_name} in range({start}, {stop}):"]
        lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
        ctx.local_names = previous_locals
        return lines

    lines = translate_statement(initializer, ctx, indent=indent)
    lines.append(f"{indent}while {translate_expression(condition, ctx)}:")
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    lines.append(f"{indent}    {translate_expression(update, ctx)}")
    return lines


def _range_loop_parts(
    initializer: JavaNode,
    condition: JavaNode,
    update: JavaNode,
    ctx: TranslationContext,
) -> tuple[str, str, str, str] | None:
    declarator = first_child_by_type(initializer, "variable_declarator")
    if declarator is None:
        return None
    name_node = declarator.child_by_field("name")
    value_node = declarator.child_by_field("value")
    condition_children = condition.children
    update_children = update.children
    if (
        name_node is None
        or value_node is None
        or len(condition_children) < 3
        or len(update_children) < 2
        or update_children[-1].text != "++"
        or condition_children[0].text != name_node.text
        or condition_children[1].text != "<"
        or update.named_children[0].text != name_node.text
    ):
        return None
    return (
        name_node.text,
        translate_field_name(name_node.text, snake_case=ctx.cfg.snake_case_fields),
        translate_expression(value_node, ctx),
        translate_expression(condition_children[2], ctx),
    )


def _translate_while(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated while statement")
    condition = node.child_by_field("condition") or node.named_children[0]
    body = node.child_by_field("body") or node.named_children[-1]
    lines = [f"{indent}while {translate_expression(condition, ctx)}:"]
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    return lines


def _translate_do_while(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated do while statement")
    body = first_child_by_type(node, "block")
    condition = first_child_by_type(node, "parenthesized_expression")
    lines = [f"{indent}while True:"]
    if body is None:
        lines.append(f"{indent}    pass")
    else:
        lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    lines.append(f"{indent}    if not ({translate_expression(condition, ctx)}):")
    lines.append(f"{indent}        break")
    return lines


def _translate_try(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated try statement")
    try_body = first_child_by_type(node, "block")
    lines = [f"{indent}try:"]
    lines.extend(
        translate_body(try_body, ctx, indent=f"{indent}    ")
        if try_body is not None
        else [f"{indent}    pass"],
    )

    for catch_clause in direct_children_by_type(node, "catch_clause"):
        lines.extend(_translate_catch(catch_clause, ctx, indent=indent))

    finally_clause = first_child_by_type(node, "finally_clause")
    if finally_clause is not None:
        finally_body = first_child_by_type(finally_clause, "block")
        lines.append(f"{indent}finally:")
        lines.extend(
            translate_body(finally_body, ctx, indent=f"{indent}    ")
            if finally_body is not None
            else [f"{indent}    pass"],
        )

    return lines


def _translate_try_with_resources(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    resources = first_child_by_type(node, "resource_specification")
    body = first_child_by_type(node, "block")
    if resources is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed try-with-resources")
        return [f"{indent}# TODO(j2py): malformed try-with-resources", f"{indent}pass"]

    resource_parts: list[str] = []
    resource_bindings: list[tuple[str, str]] = []
    for resource in direct_children_by_type(resources, "resource"):
        named = resource.named_children
        if len(named) == 1:
            resource_parts.append(translate_expression(named[0], ctx))
            continue
        if len(named) < 3:
            ctx.diagnostics.record(
                resource,
                supported=False,
                reason="malformed try-with-resources resource",
            )
            return [
                f"{indent}# TODO(j2py): malformed try-with-resources resource",
                f"{indent}pass",
            ]
        type_node, name_node, value_node = named[0], named[1], named[-1]
        raw_name = name_node.text
        py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
        py_type = translate_type(type_node.text, ctx.cfg)
        resource_parts.append(f"{translate_expression(value_node, ctx)} as {py_name}")
        resource_bindings.append((raw_name, py_type))

    if not resource_parts:
        ctx.diagnostics.record(node, supported=False, reason="try-with-resources without resources")
        return [f"{indent}# TODO(j2py): try-with-resources without resources", f"{indent}pass"]

    ctx.diagnostics.record(node, supported=True, reason="translated try-with-resources statement")
    previous_locals = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    for raw_name, py_type in resource_bindings:
        ctx.local_names.add(raw_name)
        ctx.variable_types[raw_name] = py_type
    try:
        lines = [f"{indent}with {', '.join(resource_parts)}:"]
        lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
    return lines


def _translate_synchronized(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    lock = first_child_by_type(node, "parenthesized_expression")
    body = first_child_by_type(node, "block")
    if lock is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed synchronized statement")
        return [f"{indent}# TODO(j2py): malformed synchronized statement", f"{indent}pass"]

    if lock_expression_is_this(lock):
        if not ctx.in_instance_method:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="synchronized(this) is invalid in static context",
            )
            return [
                f"{indent}# TODO(j2py): synchronized(this) in static context",
                f"{indent}pass",
            ]
        if ctx.class_state is not None:
            ctx.class_state.needs_instance_lock = True
        ctx.diagnostics.record(
            node,
            supported=True,
            reason="translated synchronized(this) to instance lock context manager",
        )
        lock_expr = f"self.{INSTANCE_LOCK_ATTR}"
    else:
        ctx.diagnostics.record(node, supported=True, reason="translated synchronized statement")
        ctx.diagnostics.warn(
            node,
            reason=(
                "non-this synchronized lock translated as context manager; "
                "verify lock semantics"
            ),
        )
        lock_expr = translate_expression(lock, ctx)

    lines = [f"{indent}with {lock_expr}:"]
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    return lines


def _translate_switch(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated switch statement")
    condition = node.child_by_field("condition")
    body = node.child_by_field("body")
    if condition is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed switch statement")
        return [f"{indent}# TODO(j2py): malformed switch statement", f"{indent}pass"]

    subject = translate_expression(condition, ctx)
    groups = list(body.named_children)
    if not groups:
        return [f"{indent}pass"]

    lines: list[str] = []
    saw_default = False
    index = 0
    while index < len(groups):
        group = groups[index]
        if is_comment(group):
            ctx.diagnostics.warn(group, reason="preserved comment")
            index += 1
            continue
        if group.type == "switch_block_statement_group":
            translated, index = _switch_statement_group(
                groups,
                start_index=index,
                ctx=ctx,
                indent=indent,
            )
            group_end_index = index - 1
        elif group.type == "switch_rule":
            translated = _switch_rule_group(group, ctx, indent=indent)
            index += 1
            group_end_index = index - 1
        else:
            ctx.diagnostics.record(
                group,
                supported=False,
                reason=f"unsupported switch group {group.type}",
            )
            return [
                f"{indent}# TODO(j2py): unsupported switch group {group.type}",
                f"{indent}pass",
            ]

        if translated is None:
            ctx.diagnostics.record(
                group,
                supported=False,
                reason="switch fall-through requires manual translation",
            )
            return [
                f"{indent}# TODO(j2py): switch fall-through requires manual translation",
                f"{indent}pass",
            ]

        labels, body_lines = translated
        if labels:
            keyword = "if" if not lines else "elif"
            lines.append(f"{indent}{keyword} {_switch_condition(subject, labels)}:")
        else:
            saw_default = True
            lines.append(f"{indent}else:")
        lines.extend(body_lines or [f"{indent}    pass"])

        if not labels and group_end_index != len(groups) - 1:
            ctx.diagnostics.record(
                group,
                supported=False,
                reason="switch default before final case requires manual translation",
            )
            return [
                (
                    f"{indent}# TODO(j2py): switch default before final case "
                    "requires manual translation"
                ),
                f"{indent}pass",
            ]

    if not saw_default:
        lines.append(f"{indent}else:")
        lines.append(f"{indent}    pass")
    return lines


def _switch_statement_group(
    groups: list[JavaNode],
    *,
    start_index: int,
    ctx: TranslationContext,
    indent: str,
) -> tuple[tuple[list[str], list[str]] | None, int]:
    labels: list[str] = []
    statements: list[JavaNode] = []
    saw_default_label = False
    index = start_index
    while index < len(groups):
        group = groups[index]
        if is_comment(group):
            statements.append(group)
            index += 1
            continue
        if group.type != "switch_block_statement_group":
            break
        label = first_child_by_type(group, "switch_label")
        if label is None:
            return None, index + 1
        group_statements = [child for child in group.named_children if child != label]
        meaningful_statements = [
            statement for statement in group_statements if not is_comment(statement)
        ]
        label_values = _switch_label_values(label, ctx)
        if label_values and not saw_default_label:
            labels.extend(label_values)
        else:
            saw_default_label = True
        statements.extend(group_statements)
        index += 1
        if meaningful_statements:
            break

    terminal_statements = [statement for statement in statements if not is_comment(statement)]
    if terminal_statements and terminal_statements[-1].type == "break_statement":
        break_statement = terminal_statements[-1]
        statements = [statement for statement in statements if statement != break_statement]
    elif terminal_statements and terminal_statements[-1].type not in {
        "return_statement",
        "throw_statement",
        "continue_statement",
    }:
        return None, index
    return (
        [] if saw_default_label else labels,
        _translate_switch_body(statements, ctx, indent=indent),
    ), index


def _switch_rule_group(
    rule: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> tuple[list[str], list[str]] | None:
    label = first_child_by_type(rule, "switch_label")
    if label is None:
        return None
    body_nodes = [child for child in rule.named_children if child != label]
    if len(body_nodes) != 1:
        return None
    body_node = body_nodes[0]
    if body_node.type == "expression_statement" and body_node.named_children:
        body_lines = [f"{indent}    {translate_expression(body_node.named_children[0], ctx)}"]
    elif body_node.type == "block":
        body_lines = translate_body(body_node, ctx, indent=f"{indent}    ")
    else:
        body_lines = translate_statement(body_node, ctx, indent=f"{indent}    ")
    return _switch_label_values(label, ctx), body_lines


def _translate_switch_body(
    statements: list[JavaNode],
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    lines: list[str] = []
    for statement in statements:
        lines.extend(translate_statement(statement, ctx, indent=f"{indent}    "))
    return lines


def _switch_label_values(label: JavaNode, ctx: TranslationContext) -> list[str]:
    return [translate_expression(child, ctx) for child in label.named_children]


def _switch_condition(subject: str, labels: list[str]) -> str:
    if len(labels) == 1:
        return f"{subject} == {labels[0]}"
    return f"{subject} in ({', '.join(labels)})"


def _translate_explicit_constructor_invocation(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    args_node = first_child_by_type(node, "argument_list")
    args = translate_expression(args_node, ctx) if args_node is not None else ""
    target = node.named_children[0] if node.named_children else None

    if target is not None and target.type == "super":
        ctx.diagnostics.record(node, supported=True, reason="translated super constructor call")
        return [f"{indent}super().__init__({args})"]

    # this(...) bodies are only emitted for @overloaded dispatch groups (ADR 0009);
    # mergeable delegations were already rewritten into default parameters.
    ctx.diagnostics.record(node, supported=True, reason="translated constructor delegation call")
    return [f"{indent}self.__init__({args})"]


def _translate_catch(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated catch clause")
    parameter = first_child_by_type(node, "catch_formal_parameter")
    body = first_child_by_type(node, "block")
    exception_type = "Exception"
    exception_name = "exc"
    if parameter is not None:
        exception_type = _catch_type(parameter, ctx)
        name_node = parameter.child_by_field("name") or first_child_by_type(parameter, "identifier")
        if name_node is not None:
            exception_name = translate_field_name(
                name_node.text,
                snake_case=ctx.cfg.snake_case_fields,
            )
    lines = [f"{indent}except {exception_type} as {exception_name}:"]
    lines.extend(
        translate_body(body, ctx, indent=f"{indent}    ")
        if body is not None
        else [f"{indent}    pass"],
    )
    return lines


def _catch_type(parameter: JavaNode, ctx: TranslationContext) -> str:
    catch_type = first_child_by_type(parameter, "catch_type")
    if catch_type is None:
        return "Exception"
    types = [child.text for child in catch_type.named_children if child.type == "type_identifier"]
    mapped = [ctx.cfg.exception_map.get(java_type, java_type) for java_type in types]
    if not mapped:
        return ctx.cfg.exception_map.get(catch_type.text, catch_type.text)
    if len(mapped) == 1:
        return mapped[0]
    return f"({', '.join(mapped)})"


def _translate_throw(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated throw statement")
    expression = node.named_children[0] if node.named_children else None
    if expression is None:
        ctx.diagnostics.record(node, supported=False, reason="throw statement without expression")
        return [f"{indent}raise RuntimeError()"]
    if expression.type == "object_creation_expression":
        return [f"{indent}raise {_translate_exception_creation(expression, ctx)}"]
    return [f"{indent}raise {translate_expression(expression, ctx)}"]


def _translate_exception_creation(node: JavaNode, ctx: TranslationContext) -> str:
    type_node = node.child_by_field("type")
    args_node = first_child_by_type(node, "argument_list")
    raw_type = type_node.text if type_node is not None else "Exception"
    py_type = ctx.cfg.exception_map.get(raw_type, raw_type)
    args = list(args_node.named_children) if args_node is not None else []
    if len(args) >= 2 and args[1].type == "identifier":
        message = translate_expression(args[0], ctx)
        cause = translate_expression(args[1], ctx)
        return f"{py_type}({message}) from {cause}"
    rendered_args = ", ".join(translate_expression(arg, ctx) for arg in args)
    return f"{py_type}({rendered_args})"
