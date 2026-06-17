"""Overload-group classification before dispatcher emission."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_members import member_python_name
from j2py.translate.class_methods import method_body, parameter_infos
from j2py.translate.class_model import _modifiers
from j2py.translate.overload_dispatch import (
    _comparison_body_form,
    _deduplicate_same_body_erased_sig,
    _dispatch_guard_for_parameter,
)
from j2py.translate.overload_merge import (
    _constructor_forward_args,
    _method_forward_args,
    _OverloadForward,
    _resolve_forward_chain,
    _resolve_pass_through_forwarding,
)
from j2py.translate.overload_signatures import _erased_overload_signature


class OverloadKind(Enum):
    """Named decision families for overloaded Java member groups."""

    MERGE_FORWARDING = "merge_forwarding"
    MERGE_IDENTICAL_OR_EQUIVALENT = "merge_identical_or_equivalent"
    VALUE_DISPATCH_SAFE = "value_dispatch_safe"
    RUNTIME_DISPATCH_SAFE = "runtime_dispatch_safe"
    STATIC_INSTANCE_COLLISION = "static_instance_collision"
    ERASURE_COLLISION_UNSAFE = "erasure_collision_unsafe"
    MANUAL_UNSUPPORTED = "manual_unsupported"


@dataclass(frozen=True)
class OverloadClassification:
    """A reviewable overload decision before code emission."""

    kind: OverloadKind
    reason: str
    erased_signatures: tuple[tuple[str, ...], ...]
    guard_signatures: tuple[tuple[str, ...], ...] = ()


def classify_overload_group(
    members: list[JavaNode],
    cfg: TranslationConfig,
) -> OverloadClassification:
    """Classify a same-Python-name Java overload group.

    The classifier intentionally mirrors the existing emission tiers without
    performing translation. It is a decision table, not a new dispatcher.
    """
    erased = tuple(_erased_overload_signature(member, cfg) for member in members)
    if len(members) < 2:
        return OverloadClassification(
            OverloadKind.MANUAL_UNSUPPORTED,
            "not an overload group",
            erased,
        )
    if any(member_python_name(member) != member_python_name(members[0]) for member in members):
        return OverloadClassification(
            OverloadKind.MANUAL_UNSUPPORTED,
            "members do not share one Python name",
            erased,
        )
    if any(
        member.type not in {"constructor_declaration", "method_declaration"} for member in members
    ):
        return OverloadClassification(
            OverloadKind.MANUAL_UNSUPPORTED,
            "unsupported member kind in overload group",
            erased,
        )
    if any(member.type != members[0].type for member in members):
        return OverloadClassification(
            OverloadKind.MANUAL_UNSUPPORTED,
            "mixed constructor and method overload group",
            erased,
        )

    static_shapes = tuple("static" in _modifiers(member) for member in members)
    if any(shape != static_shapes[0] for shape in static_shapes):
        return OverloadClassification(
            OverloadKind.STATIC_INSTANCE_COLLISION,
            "static and instance members share one Python name",
            erased,
        )

    if _is_forwarding_merge_candidate(members, cfg):
        return OverloadClassification(
            OverloadKind.MERGE_FORWARDING,
            "overload group forwards to one implementation",
            erased,
        )
    if _has_identical_or_equivalent_bodies(members, cfg):
        return OverloadClassification(
            OverloadKind.MERGE_IDENTICAL_OR_EQUIVALENT,
            "overload bodies are identical or equivalent after Python erasure",
            erased,
        )

    guard_signatures = _guard_signatures(members, cfg)
    if guard_signatures is not None and len(set(guard_signatures)) == len(guard_signatures):
        return OverloadClassification(
            OverloadKind.VALUE_DISPATCH_SAFE,
            "runtime-checkable value guards are pairwise distinct",
            erased,
            guard_signatures,
        )

    if len(set(erased)) == len(erased):
        return OverloadClassification(
            OverloadKind.RUNTIME_DISPATCH_SAFE,
            "erased Python signatures are pairwise distinct",
            erased,
        )

    return OverloadClassification(
        OverloadKind.ERASURE_COLLISION_UNSAFE,
        "overload signatures erase to indistinguishable Python runtime shapes",
        erased,
        guard_signatures or (),
    )


def _is_forwarding_merge_candidate(members: list[JavaNode], cfg: TranslationConfig) -> bool:
    if members[0].type == "constructor_declaration":
        forwards = _forward_entries_for_members(members, cfg, _constructor_forward_args)
        return _has_default_forwarding_merge(forwards)
    if any(member.type != "method_declaration" for member in members):
        return False
    forwards = _forward_entries_for_members(members, cfg, _method_forward_args)
    return (
        _has_default_forwarding_merge(forwards)
        or _resolve_pass_through_forwarding(forwards) is not None
    )


def _forward_entries_for_members(
    members: list[JavaNode],
    cfg: TranslationConfig,
    forward_args: Callable[[JavaNode], list[JavaNode] | None],
) -> list[_OverloadForward]:
    return [
        _OverloadForward(member, parameter_infos(member, cfg), forward_args(member))
        for member in members
    ]


def _has_default_forwarding_merge(forwards: list[_OverloadForward]) -> bool:
    implementations = [forward for forward in forwards if forward.forwarded is None]
    if len(implementations) != 1:
        return False
    impl = implementations[0]
    if not impl.params:
        return False
    arities = [len(forward.params) for forward in forwards]
    if len(set(arities)) != len(arities):
        return False
    by_arity = {len(forward.params): forward for forward in forwards}
    for forward in forwards:
        if forward is impl:
            continue
        vector = _resolve_forward_chain(forward, by_arity, impl)
        if vector is None or len(vector) != len(impl.params):
            return False
        prefix = len(forward.params)
        for position, entry in enumerate(vector):
            if position < prefix and entry != position:
                return False
            if position >= prefix and isinstance(entry, int):
                return False
    return True


def _has_identical_or_equivalent_bodies(
    members: list[JavaNode],
    cfg: TranslationConfig,
) -> bool:
    if any(member.type != "method_declaration" for member in members):
        return False
    param_sets = [parameter_infos(member, cfg) for member in members]
    if len({len(params) for params in param_sets}) != 1:
        return False
    if not param_sets[0]:
        return False
    raw_names = [param.raw_name for param in param_sets[0]]
    if any([param.raw_name for param in params] != raw_names for params in param_sets):
        return False

    body_texts: set[str] = set()
    for member in members:
        body = method_body(member)
        body_texts.add(body.text if body is not None else "")
    if len(body_texts) == 1:
        return True
    return _deduplicate_same_body_erased_sig(members, cfg) is not None and all(
        _comparison_body_form(member, cfg) is not None for member in members
    )


def _guard_signatures(
    members: list[JavaNode],
    cfg: TranslationConfig,
) -> tuple[tuple[str, ...], ...] | None:
    if any(member.type != "method_declaration" for member in members):
        return None
    signatures: list[tuple[str, ...]] = []
    for member in members:
        params = parameter_infos(member, cfg)
        if any(param.is_spread for param in params):
            return None
        guards = []
        for param in params:
            guard = _dispatch_guard_for_parameter(param)
            if guard is None:
                return None
            guards.append(guard)
        signatures.append(
            tuple(
                guard.condition_template if guard.condition_template is not None else "*"
                for guard in guards
            ),
        )
    return tuple(signatures)
