"""Runtime overload guard construction and rendering helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from j2py.parse.java_ast import JavaNode
from j2py.translate.class_methods import method_body
from j2py.translate.class_model import ParameterInfo
from j2py.translate.overload_signatures import _erase_py_type, _java_simple_type


@dataclass(frozen=True)
class _DispatchGuard:
    """A runtime-checkable guard for one overload parameter."""

    key: str
    specificity: int
    condition_template: str | None = None


def _member_dispatch_key(
    params: list[ParameterInfo],
    guards: list[_DispatchGuard],
) -> tuple[str, ...]:
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return ("fixed", str(len(params))) + tuple(guard.key for guard in guards)
    if spread_index != len(params) - 1:
        return ("invalid",)
    return (
        ("varargs", str(spread_index))
        + tuple(guard.key for guard in guards[:spread_index])
        + (f"{guards[spread_index].key}:spread",)
    )


def _varargs_value_guards_checkable(
    params: list[ParameterInfo],
    guards: list[_DispatchGuard],
) -> bool:
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return all(guard.condition_template is not None for guard in guards)
    if len(guards) > 1 and spread_index != len(params) - 1:
        return False
    if not all(guard.condition_template is not None for guard in guards[:spread_index]):
        return False
    spread_guard = guards[spread_index]
    return spread_guard.condition_template is not None and spread_guard.specificity > 0


def _value_dispatch_branch_order_key(
    branch: tuple[JavaNode, list[ParameterInfo], list[_DispatchGuard]],
) -> tuple[int, int, int, int]:
    _, params, guards = branch
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return (0, -sum(guard.specificity for guard in guards), len(params), 0)
    return (1, -spread_index, -sum(guard.specificity for guard in guards), len(params))


def _value_dispatch_condition(guards: list[_DispatchGuard], params: list[ParameterInfo]) -> str:
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        parts = [f"len(args) == {len(guards)}"]
        for index, guard in enumerate(guards):
            if guard.condition_template is not None:
                parts.append(guard.condition_template.format(arg=f"args[{index}]"))
        return " and ".join(parts)

    parts = [f"len(args) >= {spread_index}"]
    for index in range(spread_index):
        guard = guards[index]
        if guard.condition_template is not None:
            parts.append(guard.condition_template.format(arg=f"args[{index}]"))
    spread_guard = guards[spread_index]
    if spread_guard.condition_template is not None and spread_guard.specificity > 0:
        element_check = spread_guard.condition_template.format(arg="value")
        parts.append(f"all({element_check} for value in args[{spread_index}:])")
    return " and ".join(parts)


def _value_dispatch_assignments(
    params: list[ParameterInfo],
    *,
    member: JavaNode,
    indent: str,
) -> list[str]:
    body = method_body(member)
    body_text = body.text if body is not None else ""

    def should_assign(param: ParameterInfo) -> bool:
        return re.search(rf"\b{re.escape(param.raw_name)}\b", body_text) is not None

    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return [
            f"{indent}{param.py_name} = args[{index}]"
            for index, param in enumerate(params)
            if should_assign(param)
        ]
    lines = [
        f"{indent}{params[index].py_name} = args[{index}]"
        for index in range(spread_index)
        if should_assign(params[index])
    ]
    spread_param = params[spread_index]
    if should_assign(spread_param):
        lines.append(f"{indent}{spread_param.py_name} = args[{spread_index}:]")
    return lines


def _dispatch_guard_for_parameter(param: ParameterInfo) -> _DispatchGuard | None:
    simple = _java_simple_type(param.java_type)
    simple_guard = _JAVA_SIMPLE_GUARDS.get(simple)
    if simple_guard is not None:
        return simple_guard

    erased = _erase_py_type(param.py_type).removeprefix("*")
    base = erased.split(".")[-1]
    py_guard = _PY_TYPE_GUARDS.get(base)
    if py_guard is not None:
        return py_guard
    return _DispatchGuard(f"opaque:{base}", 0)


_CHAR_GUARD = _DispatchGuard(
    "char",
    50,
    "isinstance({arg}, str) and len({arg}) == 1",
)

_JAVA_SIMPLE_GUARDS: dict[str, _DispatchGuard] = {
    "Character": _CHAR_GUARD,
    "CharSequence": _DispatchGuard("str", 40, "isinstance({arg}, str)"),
    "String": _DispatchGuard("str", 40, "isinstance({arg}, str)"),
    "char": _CHAR_GUARD,
}

_PY_TYPE_GUARDS: dict[str, _DispatchGuard] = {
    "Any": _DispatchGuard("object", 0),
    "Callable": _DispatchGuard("Callable", 35, "callable({arg})"),
    "bool": _DispatchGuard("bool", 45, "isinstance({arg}, bool)"),
    "callable": _DispatchGuard("Callable", 35, "callable({arg})"),
    "dict": _DispatchGuard("dict", 35, "isinstance({arg}, dict)"),
    "float": _DispatchGuard(
        "float",
        35,
        "isinstance({arg}, (int, float)) and not isinstance({arg}, bool)",
    ),
    "int": _DispatchGuard(
        "int",
        36,
        "isinstance({arg}, int) and not isinstance({arg}, bool)",
    ),
    "list": _DispatchGuard("list", 35, "isinstance({arg}, list)"),
    "object": _DispatchGuard("object", 0),
    "set": _DispatchGuard("set", 35, "isinstance({arg}, set)"),
    "str": _DispatchGuard("str", 40, "isinstance({arg}, str)"),
    "type": _DispatchGuard("type", 35, "isinstance({arg}, type)"),
}
