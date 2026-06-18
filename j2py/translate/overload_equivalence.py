"""Overload body-equivalence and deduplication helpers."""

from __future__ import annotations

import re

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_methods import method_body, parameter_infos
from j2py.translate.class_model import ParameterInfo
from j2py.translate.overload_guards import (
    _dispatch_guard_for_parameter,
    _DispatchGuard,
    _member_dispatch_key,
)
from j2py.translate.overload_signatures import _erased_overload_signature


def _deduplicate_same_body_erased_sig(
    members: list[JavaNode],
    cfg: TranslationConfig,
) -> list[JavaNode] | None:
    """Reduce overloads that share an erased signature AND equivalent body to one member.

    When Java numeric-width variants (e.g. ``sort(int[])`` and ``sort(long[])``) map to
    the same Python erasure and have identical Java body text, only one representative is
    needed.

    Bodies that are not textually identical may still be *provably equivalent* under Python
    ``int`` semantics. The ``compare(byte/short/int/long)`` family is the motivating case:
    the narrow overloads return ``x - y`` while the wide ones return ``x < y ? -1 : 1``.
    Both honour the ``Comparator`` sign contract, and once the integral types erase to a
    single Python ``int`` the difference form cannot overflow, so the whole group collapses
    to one method. See :func:`_comparison_body_form`.

    Returns the reduced list when at least one deduplication occurs AND every same-erased-sig
    group is internally consistent (identical text or all recognised comparison forms over the
    same parameters). Returns None if deduplication is impossible or unnecessary.
    """
    erased = [_erased_overload_signature(member, cfg) for member in members]
    if len(set(erased)) == len(erased):
        return None  # already distinct — nothing to deduplicate

    # Per erased signature, the canonical body key and the index/form of the kept member.
    sig_to_key: dict[tuple[str, ...], str] = {}
    sig_to_repr_index: dict[tuple[str, ...], int] = {}
    sig_to_repr_form: dict[tuple[str, ...], str | None] = {}
    reduced: list[JavaNode] = []

    for member, sig in zip(members, erased, strict=True):
        form = _comparison_body_form(member, cfg)
        body = method_body(member)
        body_text = body.text.strip() if body is not None else ""
        # Recognised comparison bodies share one key so the diff/sign forms unify; everything
        # else falls back to exact text equality (the original behaviour).
        key = _COMPARISON_BODY_KEY if form is not None else body_text

        if sig not in sig_to_key:
            sig_to_key[sig] = key
            sig_to_repr_index[sig] = len(reduced)
            sig_to_repr_form[sig] = form
            reduced.append(member)
        elif sig_to_key[sig] == key:
            # Equivalent — drop the duplicate. For comparison groups prefer the explicit
            # sign form as the kept representative: it is value-identical to Java for the
            # wide integral overloads, while the difference form only matches the sign.
            if form == "sign" and sig_to_repr_form[sig] == "diff":
                reduced[sig_to_repr_index[sig]] = member
                sig_to_repr_form[sig] = "sign"
        else:
            return None  # same erased sig but inequivalent bodies → can't safely merge

    if len(reduced) == len(members):
        return None  # no deduplication actually happened
    return reduced


def _member_body_equivalence_key(member: JavaNode, cfg: TranslationConfig) -> str:
    form = _comparison_body_form(member, cfg)
    if form is not None:
        return _COMPARISON_BODY_KEY
    body = method_body(member)
    if body is None:
        return ""
    return _normalised_body_text(member, cfg, body)


def _member_body_preference_score(member: JavaNode, cfg: TranslationConfig) -> tuple[int, int]:
    """Prefer representatives whose body needs the least Java-only normalisation."""
    body = method_body(member)
    if body is None:
        return (0, 0)
    text = body.text
    params = parameter_infos(member, cfg)
    raw_names = [re.escape(param.raw_name) for param in params]
    unboxing = sum(
        len(re.findall(rf"\b{name}\s*\.\s*{method}\s*\(", text))
        for name in raw_names
        for method in _BOXED_UNBOXING_METHODS
    )
    casts = sum(len(re.findall(rf"\([^()]+\)\s*{name}\b", text)) for name in raw_names)
    return (unboxing + casts, len(text))


def _arity_guard_signature(
    params: list[ParameterInfo],
    guards: list[_DispatchGuard],
) -> tuple[int, tuple[str | None, ...]]:
    return (
        len(params),
        tuple(
            guard.condition_template if guard.condition_template is not None else "*"
            for guard in guards
        ),
    )


def _collapse_equivalent_arity_guard_members(
    members: list[JavaNode],
    cfg: TranslationConfig,
) -> list[JavaNode] | None:
    """Collapse overloads that share arity and runtime guards when bodies are equivalent.

    Motivating case: ``toIntValue(char, int)`` and ``toIntValue(Character, int)`` erase to
    the same Python guards but can share one value-dispatch branch while every Java overload
    keeps an ``@overload`` stub for review.
    """
    if any(member.type != "method_declaration" for member in members):
        return None

    groups: dict[tuple[object, ...], list[JavaNode]] = {}
    for member in members:
        params = parameter_infos(member, cfg)
        guards: list[_DispatchGuard] = []
        for param in params:
            guard = _dispatch_guard_for_parameter(param)
            if guard is None:
                return None
            guards.append(guard)
        key = (
            _member_dispatch_key(params, guards)
            if any(param.is_spread for param in params)
            else _arity_guard_signature(params, guards)
        )
        groups.setdefault(key, []).append(member)

    reduced: list[JavaNode] = []
    for group_members in groups.values():
        if len(group_members) == 1:
            reduced.append(group_members[0])
            continue
        if all(_comparison_body_form(member, cfg) is not None for member in group_members):
            return None
        body_keys = {_member_body_equivalence_key(member, cfg) for member in group_members}
        if len(body_keys) != 1:
            return None
        reduced.append(group_members[0])

    if len(reduced) == len(members):
        return None
    return reduced


_COMPARISON_BODY_KEY = "<two-param-int-comparison>"
_BOXED_UNBOXING_METHODS = frozenset(
    {
        "booleanValue",
        "byteValue",
        "shortValue",
        "intValue",
        "longValue",
        "floatValue",
        "doubleValue",
        "charValue",
    },
)
_FLOATING_FAMILY_TYPES = frozenset({"float", "double", "Float", "Double"})


def _normalised_body_text(
    member: JavaNode,
    cfg: TranslationConfig,
    body: JavaNode,
) -> str:
    text = body.text.strip()
    for param in parameter_infos(member, cfg):
        name = re.escape(param.raw_name)
        for method in _BOXED_UNBOXING_METHODS:
            text = re.sub(rf"\b{name}\s*\.\s*{method}\s*\(\s*\)", param.raw_name, text)
    if _is_floating_family_member(member, cfg):
        text = re.sub(r"\b(?:Float|Double)\b", "FloatDouble", text)
        text = re.sub(r"\b(?:float|double)\b", "floatdouble", text)
    return _normalise_whitespace(text)


def _is_floating_family_member(member: JavaNode, cfg: TranslationConfig) -> bool:
    type_names = [_base_java_type(param.java_type) for param in parameter_infos(member, cfg)]
    return_type_node = member.child_by_field("type")
    if return_type_node is not None:
        type_names.append(_base_java_type(return_type_node.text))
    floating = [name for name in type_names if name in _FLOATING_FAMILY_TYPES]
    return bool(floating) and all(name in _FLOATING_FAMILY_TYPES for name in type_names if name)


def _base_java_type(java_type: str) -> str:
    text = java_type.strip()
    while text.endswith("[]"):
        text = text[:-2].strip()
    if text.endswith("..."):
        text = text[:-3].strip()
    return text.split("<", 1)[0].strip()


def _normalise_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _comparison_body_form(member: JavaNode, cfg: TranslationConfig) -> str | None:
    """Classify a two-argument integer comparison body, or return None.

    Recognises exactly the two shapes used by the JDK/Commons ``compare(T, T)`` contract,
    over the method's own two parameters ``(p0, p1)`` in order:

    * ``"diff"`` — ``return p0 - p1;``
    * ``"sign"`` — ``if (p0 == p1) { return 0; } return p0 < p1 ? -1 : 1;``

    Both return an ``int`` whose sign orders the two values. The match is deliberately exact
    (no near-miss normalisation) so unrelated methods that happen to share an erased signature
    are never collapsed.
    """
    type_node = member.child_by_field("type")
    if type_node is None or type_node.text.strip() != "int":
        return None
    params = parameter_infos(member, cfg)
    if len(params) != 2 or any(p.is_spread for p in params):
        return None
    p0, p1 = params[0].raw_name, params[1].raw_name
    body = method_body(member)
    if body is None or body.type != "block":
        return None
    stmts = _code_children(body)

    if len(stmts) == 1 and stmts[0].type == "return_statement":
        expr = _return_value(stmts[0])
        if _is_param_binary(expr, "-", p0, p1):
            return "diff"
        return None

    if (
        len(stmts) == 2
        and stmts[0].type == "if_statement"
        and stmts[1].type == "return_statement"
        and _is_zero_guard(stmts[0], p0, p1)
        and _is_sign_ternary(_return_value(stmts[1]), p0, p1)
    ):
        return "sign"
    return None


_COMMENT_NODE_TYPES = frozenset({"line_comment", "block_comment"})


def _code_children(node: JavaNode) -> list[JavaNode]:
    """Named children with tree-sitter comment nodes removed.

    tree-sitter-java keeps ``line_comment`` / ``block_comment`` as named children, so a
    comment inside a body or block would otherwise inflate the statement count and defeat
    the exact shape match.
    """
    return [child for child in node.named_children if child.type not in _COMMENT_NODE_TYPES]


def _unwrap_parens(node: JavaNode | None) -> JavaNode | None:
    """Strip any ``(...)`` wrappers so the inner expression can be matched directly."""
    while node is not None and node.type == "parenthesized_expression":
        children = _code_children(node)
        node = children[0] if children else None
    return node


def _return_value(return_stmt: JavaNode) -> JavaNode | None:
    children = _code_children(return_stmt)
    return children[0] if children else None


def _single_return(node: JavaNode | None) -> JavaNode | None:
    """The lone return of a consequence — a bare ``return ...;`` or a block with one."""
    if node is None:
        return None
    if node.type == "return_statement":
        return node
    if node.type == "block":
        body = _code_children(node)
        if len(body) == 1 and body[0].type == "return_statement":
            return body[0]
    return None


def _is_param_identifier(node: JavaNode | None, name: str) -> bool:
    return node is not None and node.type == "identifier" and node.text == name


def _is_param_binary(node: JavaNode | None, operator: str, left: str, right: str) -> bool:
    """True when ``node`` is ``left <operator> right`` over the two named parameters."""
    node = _unwrap_parens(node)
    if node is None or node.type != "binary_expression":
        return False
    op = node.child_by_field("operator")
    if op is None or op.text != operator:
        return False
    return _is_param_identifier(node.child_by_field("left"), left) and _is_param_identifier(
        node.child_by_field("right"), right
    )


def _is_zero_guard(if_stmt: JavaNode, p0: str, p1: str) -> bool:
    """True for ``if (p0 == p1) return 0;`` — braced or not, ``==`` symmetric, no else."""
    if if_stmt.child_by_field("alternative") is not None:
        return False
    condition = if_stmt.child_by_field("condition")
    if not (_is_param_binary(condition, "==", p0, p1) or _is_param_binary(condition, "==", p1, p0)):
        return False
    return_stmt = _single_return(if_stmt.child_by_field("consequence"))
    if return_stmt is None:
        return False
    value = _return_value(return_stmt)
    return value is not None and value.text.strip() == "0"


def _is_sign_ternary(node: JavaNode | None, p0: str, p1: str) -> bool:
    """True for ``p0 < p1 ? -1 : 1``."""
    node = _unwrap_parens(node)
    if node is None or node.type != "ternary_expression":
        return False
    if not _is_param_binary(node.child_by_field("condition"), "<", p0, p1):
        return False
    consequence = node.child_by_field("consequence")
    alternative = node.child_by_field("alternative")
    return (
        consequence is not None
        and alternative is not None
        and consequence.text.strip() == "-1"
        and alternative.text.strip() == "1"
    )
