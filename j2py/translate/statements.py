"""Statement emission for the rule-based skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import infer_expression_py_type, translate_expression
from j2py.translate.node_utils import direct_children_by_type, first_child_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import is_var_type, translate_type

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
    """Return True when current-class instance members use ``synchronized (this)``."""
    body = class_node.child_by_field("body")
    if body is None:
        return False
    for member in body.named_children:
        if member.type == "constructor_declaration":
            if _member_uses_synchronized_this(member):
                return True
            continue
        if (
            member.type == "method_declaration"
            and not _has_static_modifier(member)
            and _member_uses_synchronized_this(member)
        ):
            return True
    return False


def instance_lock_init_line(*, indent: str = "        ") -> str:
    return f"{indent}self.{INSTANCE_LOCK_ATTR} = threading.Lock()"


def _has_static_modifier(node: JavaNode) -> bool:
    for modifiers in node.children_by_type("modifiers"):
        if "static" in modifiers.text.split():
            return True
    return False


def _member_uses_synchronized_this(member: JavaNode) -> bool:
    body = member.child_by_field("body")
    if body is None:
        body = first_child_by_type(member, "block", "constructor_body")
    return body is not None and _node_uses_synchronized_this(body)


def _node_uses_synchronized_this(node: JavaNode) -> bool:
    if node.type in TYPE_DECLARATION_NODES or node.type == "class_body":
        return False
    if node.type == "synchronized_statement":
        lock = first_child_by_type(node, "parenthesized_expression")
        return lock is not None and lock_expression_is_this(lock)
    return any(_node_uses_synchronized_this(child) for child in node.named_children)


def translate_body(body: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    lines: list[str] = []
    for statement in body.named_children:
        lines.extend(translate_statement(statement, ctx, indent=indent))
    if _body_needs_pass(lines):
        lines.append(f"{indent}pass")
    return lines


def _body_needs_pass(lines: list[str]) -> bool:
    if not lines:
        return True
    return all(not line.strip() or line.lstrip().startswith("#") for line in lines)


def _with_expression_comments(line: str, ctx: TranslationContext) -> str:
    if not ctx.pending_expression_comments:
        return line
    comment = "; ".join(ctx.pending_expression_comments)
    ctx.pending_expression_comments.clear()
    return f"{line}  # {comment}"


def translate_statement(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    if is_comment(node):
        ctx.diagnostics.warn(node, reason="preserved comment")
        if not ctx.cfg.emit_line_comments:
            return []
        return translate_comment(node, indent=indent)

    if node.type == "expression_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated expression statement")
        expr = node.named_children[0] if node.named_children else node
        return [_with_expression_comments(f"{indent}{translate_expression(expr, ctx)}", ctx)]

    if node.type == "return_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated return statement")
        if not node.named_children:
            return [f"{indent}return"]
        return [
            _with_expression_comments(
                f"{indent}return {translate_expression(node.named_children[0], ctx)}",
                ctx,
            )
        ]

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
    java_type = type_node.text if type_node is not None else "Object"

    lines: list[str] = []
    for declarator in direct_children_by_type(node, "variable_declarator"):
        name_node = declarator.child_by_field("name")
        if name_node is None:
            continue
        raw_name = name_node.text
        py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
        ctx.local_names.add(raw_name)
        value_node = declarator.child_by_field("value")
        if is_var_type(java_type):
            inferred = infer_expression_py_type(value_node, ctx) if value_node is not None else None
            py_type = inferred or "object"
        else:
            py_type = translate_type(java_type, ctx.cfg)
        if ctx.cfg.emit_type_hints:
            ctx.diagnostics.imports.need_type_annotation(py_type)
        ctx.variable_types[raw_name] = py_type
        ctx.variable_java_types[raw_name] = java_type
        value = translate_expression(value_node, ctx) if value_node else "None"
        if not ctx.cfg.emit_type_hints:
            lines.append(_with_expression_comments(f"{indent}{py_name} = {value}", ctx))
        elif value in {"[]", "{}", "set()"}:
            lines.append(_with_expression_comments(f"{indent}{py_name}: {py_type} = {value}", ctx))
        else:
            lines.append(_with_expression_comments(f"{indent}{py_name} = {value}", ctx))
    return lines


def _translate_enhanced_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    from j2py.translate.stmt_control import _translate_enhanced_for as impl

    return impl(node, ctx, indent=indent)


def _translate_if(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
    keyword: str = "if",
) -> list[str]:
    from j2py.translate.stmt_control import _translate_if as impl

    return impl(node, ctx, indent=indent, keyword=keyword)


def _translate_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    from j2py.translate.stmt_control import _translate_for as impl

    return impl(node, ctx, indent=indent)


def _translate_while(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    from j2py.translate.stmt_control import _translate_while as impl

    return impl(node, ctx, indent=indent)


def _translate_do_while(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    from j2py.translate.stmt_control import _translate_do_while as impl

    return impl(node, ctx, indent=indent)


def _translate_try(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    from j2py.translate.stmt_exceptions import _translate_try as impl

    return impl(node, ctx, indent=indent)


def _translate_try_with_resources(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    from j2py.translate.stmt_exceptions import _translate_try_with_resources as impl

    return impl(node, ctx, indent=indent)


def _translate_synchronized(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    from j2py.translate.stmt_sync import _translate_synchronized as impl

    return impl(node, ctx, indent=indent)


def _translate_switch(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    from j2py.translate.stmt_switch import _translate_switch as impl

    return impl(node, ctx, indent=indent)


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
    from j2py.translate.stmt_exceptions import _translate_catch as impl

    return impl(node, ctx, indent=indent)


def _translate_throw(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    from j2py.translate.stmt_exceptions import _translate_throw as impl

    return impl(node, ctx, indent=indent)
