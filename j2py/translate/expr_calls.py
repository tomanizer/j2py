"""Method invocation and Java standard-library call shims."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.java_types import java_type_of_value
from j2py.translate.node_utils import first_child_by_type, unwrap_parens
from j2py.translate.rules.naming import (
    _receiver_simple_name,
    translate_attribute_method_name,
    translate_method_name,
)
from j2py.translate.rules.types import (
    is_api_get_receiver_type,
    is_indexed_predicate_get_receiver_java_type,
    is_indexed_predicate_get_receiver_type,
    is_map_like_type,
    type_simple_name,
)


def _route_static_instance_collision_to_static(
    py_method: str,
    args: str,
    ctx: TranslationContext,
) -> bool:
    """Whether a receiverless collision call should dispatch to the static rename."""
    if py_method not in ctx.static_instance_static_aliases:
        return True
    if args:
        return True
    instance_zero = py_method in ctx.static_instance_instance_zero_arg_names
    static_zero = py_method in ctx.static_instance_static_zero_arg_names
    if static_zero and not instance_zero:
        return True
    if instance_zero and not static_zero:
        return False
    if static_zero and instance_zero:
        return not ctx.in_instance_method
    return False


def _translate_method_invocation(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_streams import _translate_stream_pipeline

    stream_pipeline = _translate_stream_pipeline(node, ctx)
    if stream_pipeline is not None:
        return stream_pipeline

    args_node = first_child_by_type(node, "argument_list")

    named = node.named_children
    if args_node is None or len(named) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed method invocation")
        return f"__j2py_todo__({node.text!r})"

    arg_nodes = _argument_nodes(args_node)
    arg_expressions = [_translate_argument(child, ctx) for child in arg_nodes]
    args = ", ".join(arg_expressions)

    args_index = named.index(args_node)
    method_node = named[args_index - 1]
    method_name = method_node.text
    receiver_nodes = named[: args_index - 1]
    raw_receiver = receiver_nodes[0].text if receiver_nodes else ""

    if not receiver_nodes and method_name in ctx.static_method_imports:
        static_call = _translate_static_imported_method(
            node,
            imported_name=ctx.static_method_imports[method_name],
            arg_nodes=arg_nodes,
            args=arg_expressions,
            ctx=ctx,
        )
        if static_call is not None:
            return static_call

    static_call = _translate_static_method_invocation(
        node,
        raw_receiver=raw_receiver,
        method_name=method_name,
        arg_nodes=arg_nodes,
        args=arg_expressions,
        ctx=ctx,
    )
    if static_call is not None:
        return static_call

    if raw_receiver == "System.out" and method_name == "println":
        return f"print({args})"

    receiver = translate_expression(receiver_nodes[0], ctx) if receiver_nodes else ""

    if method_name == "add" and receiver:
        from j2py.translate.expr_types import _expression_py_type, _is_list_type

        receiver_type = _expression_py_type(receiver_nodes[0], ctx) if receiver_nodes else None
        if receiver_type is not None and _is_list_type(receiver_type):
            return f"{receiver}.append({args})"

    if method_name in {"size", "length"} and receiver and not args:
        return f"len({receiver})"

    if method_name == "isEmpty" and receiver and not args:
        return f"not {receiver}"

    if (
        method_name == "contains"
        and receiver
        and args
        and len(arg_expressions) == 1
        and receiver_nodes[0].type != "super"
        and not raw_receiver.split(".")[-1][:1].isupper()
    ):
        return f"{args} in {receiver}"

    if method_name == "toArray" and receiver:
        return f"list({receiver})"

    if method_name == "get" and receiver and args:
        return _translate_get_invocation(
            node,
            receiver=receiver,
            receiver_nodes=receiver_nodes,
            raw_receiver=raw_receiver,
            arg_nodes=arg_nodes,
            arg_expressions=arg_expressions,
            args=args,
            ctx=ctx,
        )

    if method_name == "equals" and receiver and args:
        if len(arg_nodes) == 2 and raw_receiver.split(".")[-1][:1].isupper():
            return f"{arg_expressions[0]} == {arg_expressions[1]}"
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

    if method_name == "equalsIgnoreCase" and receiver and args and len(arg_nodes) == 1:
        return f"{receiver}.lower() == {args}.lower()"

    if method_name == "toString" and receiver and not args:
        return f"str({receiver})"

    if method_name == "hashCode" and receiver and not args:
        return f"hash({receiver})"

    if method_name == "charAt" and receiver and args and len(arg_nodes) == 1:
        return f"{receiver}[{args}]"

    if method_name == "substring" and receiver and args:
        if len(arg_nodes) == 1:
            return f"{receiver}[{args}:]"
        if len(arg_nodes) == 2:
            return f"{receiver}[{arg_expressions[0]}:{arg_expressions[1]}]"

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

    if receiver in {"self", ""}:
        py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
        static_py_method = ctx.static_instance_static_aliases.get(py_method, py_method)
        if (
            not receiver
            and static_py_method in ctx.class_static_methods
            and ctx.containing_class_name
            and _route_static_instance_collision_to_static(py_method, args, ctx)
        ):
            return f"{ctx.containing_class_name}.{static_py_method}({args})"
        enclosing_class = ctx.enclosing_static_dispatch.get(py_method)
        if (
            not receiver
            and enclosing_class
            and _route_static_instance_collision_to_static(py_method, args, ctx)
        ):
            return f"{enclosing_class}.{static_py_method}({args})"
        if not receiver and method_name in ctx.self_dispatch_methods and ctx.in_instance_method:
            return f"self.{py_method}({args})"
        if (
            not receiver
            and method_name in ctx.static_dispatch_methods
            and ctx.static_dispatch_class_name
            and _route_static_instance_collision_to_static(py_method, args, ctx)
        ):
            return f"{ctx.static_dispatch_class_name}.{static_py_method}({args})"
    else:
        if receiver_nodes and _receiver_is_declared_type(receiver_nodes[0], ctx):
            py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
        else:
            py_method = translate_attribute_method_name(
                method_name,
                snake_case=ctx.cfg.snake_case_methods,
            )
    if receiver:
        return f"{receiver}.{py_method}({args})"
    if ctx.in_instance_method and py_method in ctx.class_methods:
        return f"self.{py_method}({args})"
    return f"{py_method}({args})"


def _translate_get_invocation(
    node: JavaNode,
    *,
    receiver: str,
    receiver_nodes: list[JavaNode],
    raw_receiver: str,
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str:
    from j2py.translate.expr_types import (
        _expression_py_type,
        _is_list_type,
        _is_this_receiver,
    )

    if len(arg_expressions) != 1:
        return f"{receiver}.get({args})"

    if receiver_nodes and receiver_nodes[0].type == "super":
        return f"{receiver}.get({args})"

    if (
        receiver_nodes
        and receiver_nodes[0].type in {"this", "field_access"}
        and "get" in ctx.class_method_return_types
        and _is_this_receiver(receiver_nodes[0])
    ):
        return f"{receiver}.get({args})"

    receiver_type = _expression_py_type(receiver_nodes[0], ctx) if receiver_nodes else None
    if receiver_type is not None and _is_list_type(receiver_type):
        return f"{receiver}[{args}]"
    if receiver_type is not None and is_map_like_type(receiver_type):
        return f"{receiver}.get({args})"
    if receiver_type is not None and is_api_get_receiver_type(receiver_type):
        return f"{receiver}.get({args})"
    if receiver_type is not None and is_indexed_predicate_get_receiver_type(receiver_type):
        return f"{receiver}.get({args})"
    if receiver_nodes:
        java_receiver_type = java_type_of_value(receiver_nodes[0], ctx)
        if java_receiver_type is not None and is_indexed_predicate_get_receiver_java_type(
            java_receiver_type,
        ):
            return f"{receiver}.get({args})"
    if raw_receiver.split(".")[-1][:1].isupper():
        return f"{receiver}.get({args})"
    ctx.diagnostics.record(
        node,
        supported=False,
        reason="ambiguous get invocation requires receiver collection type",
    )
    return f"{receiver}.get({args})"


def _receiver_is_declared_type(node: JavaNode, ctx: TranslationContext) -> bool:
    from j2py.translate.expr_types import _expression_py_type

    receiver_type = _expression_py_type(node, ctx)
    if receiver_type is None:
        return False
    simple = type_simple_name(receiver_type)
    if ctx.containing_class_name in {simple, receiver_type}:
        return True
    return simple in ctx.declared_type_fields or receiver_type in ctx.declared_type_fields


def _argument_nodes(args_node: JavaNode) -> list[JavaNode]:
    return [child for child in args_node.named_children if not is_comment(child)]


_ASSIGN_OR_UPDATE = frozenset({"assignment_expression", "update_expression"})


def _translate_argument(node: JavaNode, ctx: TranslationContext) -> str:
    inner = unwrap_parens(node)
    if inner.type in _ASSIGN_OR_UPDATE:
        from j2py.translate.expr_ops import _desugar_embedded_assign

        return _desugar_embedded_assign(inner, ctx)
    return translate_expression(node, ctx)


def _translate_static_method_invocation(
    node: JavaNode,
    *,
    raw_receiver: str,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    receiver = _receiver_simple_name(raw_receiver)
    known_receivers = {
        "Arrays",
        "Character",
        "Collections",
        "Double",
        "Integer",
        "Long",
        "Math",
        "Objects",
        "Preconditions",
        "String",
    }
    if receiver not in known_receivers:
        return None

    if receiver == "Math":
        if method_name == "abs" and len(args) == 1:
            return f"abs({args[0]})"
        if method_name == "max" and len(args) == 2:
            return f"max({args[0]}, {args[1]})"
        if method_name == "min" and len(args) == 2:
            return f"min({args[0]}, {args[1]})"
        if method_name == "pow" and len(args) == 2:
            return f"pow({args[0]}, {args[1]})"
        if method_name in {"sqrt", "floor", "ceil", "log"} and len(args) == 1:
            ctx.diagnostics.imports.need_math()
            return f"math.{method_name}({args[0]})"
        if method_name == "round" and len(args) == 1:
            ctx.diagnostics.imports.need_math()
            return f"math.floor({args[0]} + 0.5)"

    if receiver == "Integer":
        if method_name == "compare" and len(args) == 2:
            return f"({args[0]} > {args[1]}) - ({args[0]} < {args[1]})"
        if method_name == "parseInt" and len(args) in {1, 2}:
            return f"int({', '.join(args)})"
        if method_name == "valueOf" and len(args) == 1:
            return f"int({args[0]})"
        if method_name == "toString" and len(args) == 1:
            return f"str({args[0]})"
        if method_name == "toBinaryString" and len(args) == 1:
            return f"format({args[0]}, 'b')"
        if method_name == "toHexString" and len(args) == 1:
            return f"format({args[0]}, 'x')"

    if receiver == "Character":
        if method_name == "valueOf" and len(args) == 1:
            return args[0]
        if method_name == "toString" and len(args) == 1:
            return f"str({args[0]})"
        char_predicate = _translate_character_char_predicate(
            node,
            method_name,
            arg_nodes,
            args,
            ctx,
        )
        if char_predicate is not None:
            return char_predicate

    if receiver == "Long" and method_name == "parseLong" and len(args) == 1:
        return f"int({args[0]})"

    if receiver == "Double" and method_name == "parseDouble" and len(args) == 1:
        return f"float({args[0]})"

    if receiver == "String":
        if method_name == "valueOf" and len(args) == 1:
            return f"str({args[0]})"
        if method_name == "format" and args:
            format_args = args[1:] if arg_nodes and _is_locale_argument(arg_nodes[0]) else args
            return _translate_string_format(format_args)

    if receiver == "Collections":
        if method_name == "sort" and len(args) == 1:
            return f"{args[0]}.sort()"
        if method_name == "reverse" and len(args) == 1:
            return f"{args[0]}.reverse()"
        if method_name == "unmodifiableList" and len(args) == 1:
            ctx.diagnostics.warn(
                node,
                reason=(
                    "Collections.unmodifiableList translated as original list; verify mutability"
                ),
            )
            return args[0]

    if receiver == "Arrays":
        if method_name == "asList":
            return f"[{', '.join(args)}]"
        if method_name == "stream" and len(args) == 1:
            return f"iter({args[0]})"
        if method_name == "equals" and len(args) == 2:
            return f"{args[0]} == {args[1]}"

    if receiver == "Objects":
        if method_name == "requireNonNull" and arg_nodes:
            return args[0]
        if method_name == "equals" and len(args) == 2:
            return f"{args[0]} == {args[1]}"
        if method_name == "isNull" and len(args) == 1:
            return f"{args[0]} is None"
        if method_name == "nonNull" and len(args) == 1:
            return f"{args[0]} is not None"

    if receiver == "Preconditions":
        if method_name == "checkNotNull" and args:
            return args[0]
        if method_name in {"checkState", "checkArgument"} and args:
            if len(args) == 1:
                return f"assert {args[0]}"
            message = _translate_string_format(args[1:])
            return f"assert {args[0]}, {message}"

    return None


def _translate_static_imported_method(
    node: JavaNode,
    *,
    imported_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    from j2py.translate.rules.naming import translate_class_name, translate_method_name

    raw_receiver, method_name = imported_name.rsplit(".", 1)
    result = _translate_static_method_invocation(
        node,
        raw_receiver=raw_receiver,
        method_name=method_name,
        arg_nodes=arg_nodes,
        args=args,
        ctx=ctx,
    )
    if result is not None:
        return result
    # Fallback: emit ClassName.method_name(args) for unknown receiver classes so the
    # output is always syntactically valid and reviewable rather than a bare call.
    class_name = translate_class_name(raw_receiver.rsplit(".", 1)[-1])
    py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
    return f"{class_name}.{py_method}({', '.join(args)})"


_CHARACTER_CHAR_PREDICATES: dict[str, str] = {
    "isDigit": "isdigit",
    "isLetter": "isalpha",
    "isLetterOrDigit": "isalnum",
    "isLowerCase": "islower",
    "isUpperCase": "isupper",
    "isWhitespace": "isspace",
}


def _translate_character_char_predicate(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    if len(args) != 1:
        return None
    predicate = _CHARACTER_CHAR_PREDICATES.get(method_name)
    if predicate is None:
        return None
    arg = args[0]
    simple_arg_nodes = {"identifier", "field_access", "character_literal", "string_literal"}
    if arg_nodes and arg_nodes[0].type not in simple_arg_nodes:
        ctx.diagnostics.warn(
            node,
            reason=(
                f"Character.{method_name} argument evaluated twice in Python "
                "translation; verify side effects"
            ),
        )
    return f"(len({arg}) == 1 and {arg}.{predicate}())"


def _translate_string_format(args: list[str]) -> str:
    if len(args) == 1:
        return args[0]
    if len(args) == 2:
        return f"{args[0]} % {args[1]}"
    return f"{args[0]} % ({', '.join(args[1:])})"


def _is_locale_argument(node: JavaNode) -> bool:
    parts = node.text.split(".")
    return any(part == "Locale" for part in parts[:-1]) or node.text == "Locale"
