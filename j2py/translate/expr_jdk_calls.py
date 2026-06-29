"""Java standard-library method call lowering helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.java_types import java_expression_type, java_type_simple_name
from j2py.translate.rules.naming import _receiver_simple_name

StaticCallTranslator: TypeAlias = Callable[
    [JavaNode, str, list[JavaNode], list[str], TranslationContext],
    str | None,
]
InstanceCallTranslator: TypeAlias = Callable[
    [
        JavaNode,
        str,
        str,
        list[JavaNode],
        list[JavaNode],
        list[str],
        str,
        TranslationContext,
    ],
    str | None,
]


def translate_known_static_method_invocation(
    node: JavaNode,
    *,
    raw_receiver: str,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    receiver = _receiver_simple_name(raw_receiver)
    translator = _STATIC_CALL_TRANSLATORS.get(receiver)
    if translator is None:
        return None
    return translator(node, method_name, arg_nodes, args, ctx)


def translate_jdk_instance_method_invocation(
    node: JavaNode,
    *,
    method_name: str,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    translator = _INSTANCE_CALL_TRANSLATORS.get(method_name)
    if translator is None:
        return None
    return translator(
        node,
        receiver,
        raw_receiver,
        receiver_nodes,
        arg_nodes,
        arg_expressions,
        args,
        ctx,
    )


def translate_string_format(args: list[str]) -> str:
    if len(args) == 1:
        return args[0]
    if len(args) == 2:
        return f"{args[0]} % {args[1]}"
    return f"{args[0]} % ({', '.join(args[1:])})"


def _translate_math_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    return _translate_math_call(method_name, args, ctx)


def _translate_integer_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    return _translate_integer_call(method_name, args)


def _translate_character_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    if method_name == "valueOf" and len(args) == 1:
        return args[0]
    if method_name == "toString" and len(args) == 1:
        return f"str({args[0]})"
    return _translate_character_char_predicate(node, method_name, arg_nodes, args, ctx)


def _translate_long_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    if method_name == "parseLong" and len(args) == 1:
        return f"int({args[0]})"
    return None


def _translate_double_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    if method_name == "parseDouble" and len(args) == 1:
        return f"float({args[0]})"
    return None


def _translate_string_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    if method_name == "valueOf" and len(args) == 1:
        return f"str({args[0]})"
    if method_name == "format" and args:
        format_args = args[1:] if arg_nodes and _is_locale_argument(arg_nodes[0]) else args
        return translate_string_format(format_args)
    return None


def _translate_collections_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    return _translate_collections_call(node, method_name, args, ctx)


def _translate_arrays_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    return _translate_arrays_call(method_name, args)


def _translate_objects_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    return _translate_objects_call(method_name, arg_nodes, args)


def _translate_preconditions_static_call(
    node: JavaNode,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    return _translate_preconditions_call(method_name, args)


def _translate_len_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"len({receiver})"
    return None


def _translate_is_empty_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"not {receiver}"
    return None


def _translate_contains_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if (
        args
        and len(arg_expressions) == 1
        and receiver_nodes[0].type != "super"
        and not raw_receiver.split(".")[-1][:1].isupper()
    ):
        return f"{args} in {receiver}"
    return None


def _translate_to_array_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    return f"list({receiver})"


def _translate_clone_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"list({receiver})"
    return None


def _translate_equals_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args:
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
    return None


def _translate_equals_ignore_case_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args and len(arg_nodes) == 1:
        return f"{receiver}.lower() == {args}.lower()"
    return None


def _translate_to_string_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"str({receiver})"
    return None


def _translate_hash_code_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"hash({receiver})"
    return None


def _translate_char_at_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args and len(arg_nodes) == 1:
        return f"{receiver}[{args}]"
    return None


def _translate_starts_with_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args:
        return f"{receiver}.startswith({args})"
    return None


def _translate_substring_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return None
    if len(arg_nodes) == 1:
        return f"{receiver}[{args}:]"
    if len(arg_nodes) == 2:
        return f"{receiver}[{arg_expressions[0]}:{arg_expressions[1]}]"
    return None


def _translate_ends_with_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args:
        return f"{receiver}.endswith({args})"
    return None


def _translate_trim_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"{receiver}.strip()"
    return None


def _translate_to_char_array_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"list({receiver})"
    return None


def _translate_char_value_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args or not receiver_nodes:
        return None
    receiver_type = java_expression_type(receiver_nodes[0], ctx)
    if receiver_type is None:
        receiver_type = ctx.variable_java_types.get(raw_receiver) or ctx.variable_java_types.get(
            receiver,
        )
    if receiver_type is not None and java_type_simple_name(receiver_type) == "Character":
        return receiver
    return None


def _translate_index_of_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args and not raw_receiver.split(".")[-1][:1].isupper():
        return f"{receiver}.find({args})"
    return None


def _translate_to_lower_case_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"{receiver}.lower()"
    return None


def _translate_to_upper_case_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if not args:
        return f"{receiver}.upper()"
    return None


def _translate_compare_to_call(
    node: JavaNode,
    receiver: str,
    raw_receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if args:
        return f"({receiver} > {args}) - ({receiver} < {args})"
    return None


def _translate_math_call(
    method_name: str,
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
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
    return None


def _translate_integer_call(method_name: str, args: list[str]) -> str | None:
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
    return None


def _translate_collections_call(
    node: JavaNode,
    method_name: str,
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    if method_name == "sort" and len(args) == 1:
        return f"{args[0]}.sort()"
    if method_name == "reverse" and len(args) == 1:
        return f"{args[0]}.reverse()"
    if method_name == "unmodifiableList" and len(args) == 1:
        ctx.diagnostics.warn(
            node,
            reason=("Collections.unmodifiableList translated as original list; verify mutability"),
        )
        return args[0]
    return None


def _translate_arrays_call(method_name: str, args: list[str]) -> str | None:
    if method_name == "asList":
        return f"[{', '.join(args)}]"
    if method_name == "copyOfRange" and len(args) == 3:
        return f"list({args[0]}[{args[1]}:{args[2]}])"
    if method_name == "stream" and len(args) == 1:
        return f"iter({args[0]})"
    if method_name == "equals" and len(args) == 2:
        return f"{args[0]} == {args[1]}"
    return None


def _translate_objects_call(
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
) -> str | None:
    if method_name == "requireNonNull" and arg_nodes:
        return args[0]
    if method_name == "equals" and len(args) == 2:
        return f"{args[0]} == {args[1]}"
    if method_name == "isNull" and len(args) == 1:
        return f"{args[0]} is None"
    if method_name == "nonNull" and len(args) == 1:
        return f"{args[0]} is not None"
    return None


def _translate_preconditions_call(method_name: str, args: list[str]) -> str | None:
    if method_name == "checkNotNull" and args:
        return args[0]
    if method_name in {"checkState", "checkArgument"} and args:
        if len(args) == 1:
            return f"assert {args[0]}"
        message = translate_string_format(args[1:])
        return f"assert {args[0]}, {message}"
    return None


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


def _is_locale_argument(node: JavaNode) -> bool:
    parts = node.text.split(".")
    return any(part == "Locale" for part in parts[:-1]) or node.text == "Locale"


_STATIC_CALL_TRANSLATORS: dict[str, StaticCallTranslator] = {
    "Arrays": _translate_arrays_static_call,
    "Character": _translate_character_static_call,
    "Collections": _translate_collections_static_call,
    "Double": _translate_double_static_call,
    "Integer": _translate_integer_static_call,
    "Long": _translate_long_static_call,
    "Math": _translate_math_static_call,
    "Objects": _translate_objects_static_call,
    "Preconditions": _translate_preconditions_static_call,
    "String": _translate_string_static_call,
}


_INSTANCE_CALL_TRANSLATORS: dict[str, InstanceCallTranslator] = {
    "charValue": _translate_char_value_call,
    "charAt": _translate_char_at_call,
    "clone": _translate_clone_call,
    "compareTo": _translate_compare_to_call,
    "contains": _translate_contains_call,
    "endsWith": _translate_ends_with_call,
    "equals": _translate_equals_call,
    "equalsIgnoreCase": _translate_equals_ignore_case_call,
    "hashCode": _translate_hash_code_call,
    "indexOf": _translate_index_of_call,
    "isEmpty": _translate_is_empty_call,
    "length": _translate_len_call,
    "size": _translate_len_call,
    "startsWith": _translate_starts_with_call,
    "substring": _translate_substring_call,
    "toArray": _translate_to_array_call,
    "toCharArray": _translate_to_char_array_call,
    "toLowerCase": _translate_to_lower_case_call,
    "toString": _translate_to_string_call,
    "toUpperCase": _translate_to_upper_case_call,
    "trim": _translate_trim_call,
}
