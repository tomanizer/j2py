"""Static method invocation and static-import call helpers."""

from __future__ import annotations

import re
from dataclasses import replace

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_jdk_calls import translate_known_static_method_invocation
from j2py.translate.member_resolution import (
    JavaMemberBinding,
    configured_member_binding_for_receiver,
    static_import_binding,
    static_import_method_fallback,
)
from j2py.translate.name_resolution import scope_from_context
from j2py.translate.rules.naming import translate_method_name

_TYPE_RECEIVER_SEGMENT = re.compile(r"[A-Z][A-Za-z_0-9]*\Z")


def _qualify_file_type_owner(
    binding: JavaMemberBinding, ctx: TranslationContext
) -> JavaMemberBinding:
    """Qualify a static-import owner that is a type declared in the current file.

    A wildcard or explicit static import of a *nested* class member (e.g.
    ``import static Outer.Validators.*``) binds the owner to the bare nested name
    (``Validators``). That name is not a module global in Python, so the fallback
    must address it through its enclosing class (``Outer.Validators``). Top-level
    owners map to themselves and are left unchanged.
    """
    owner = binding.python_owner
    if owner is None or "." in owner or not ctx.in_method:
        return binding
    qualified = ctx.name_resolver.bindings.file_type_paths.get(owner)
    if qualified is None or qualified == owner:
        return binding
    return replace(binding, python_owner=qualified)


def _alias_static_instance_member(
    binding: JavaMemberBinding,
    ctx: TranslationContext,
) -> JavaMemberBinding:
    owner = binding.python_owner or binding.owner
    aliases = ctx.module_static_instance_static_aliases.get(owner)
    if aliases is None:
        aliases = ctx.module_static_instance_static_aliases.get(owner.rsplit(".", 1)[-1])
    if not aliases:
        return binding
    py_member = translate_method_name(binding.member, snake_case=ctx.cfg.snake_case_methods)
    alias = aliases.get(py_member)
    if alias is None:
        return binding
    return replace(binding, python_member=alias)


def _request_runtime_type_import(import_line: str, kind: str, ctx: TranslationContext) -> None:
    if ctx.in_method_body and kind == "package_type":
        ctx.body_local_imports.add(import_line)
    else:
        ctx.diagnostics.imports.need_line(import_line)


def _is_type_receiver_segment(owner: str) -> bool:
    return _TYPE_RECEIVER_SEGMENT.fullmatch(owner) is not None


def translate_static_method_invocation(
    node: JavaNode,
    *,
    raw_receiver: str,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    known = translate_known_static_method_invocation(
        node,
        raw_receiver=raw_receiver,
        method_name=method_name,
        arg_nodes=arg_nodes,
        args=args,
        ctx=ctx,
    )
    if known is not None:
        return known
    if raw_receiver:
        binding = configured_member_binding_for_receiver(raw_receiver, method_name, ctx)
        if binding is not None and binding.kind in {"method", "unknown"}:
            return static_import_method_fallback(
                _alias_static_instance_member(_qualify_file_type_owner(binding, ctx), ctx),
                args,
                ctx.cfg,
            )
        owner = raw_receiver.rsplit(".", 1)[-1]
        aliases = ctx.module_static_instance_static_aliases.get(owner)
        if aliases:
            py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
            alias = aliases.get(py_method)
            if alias is not None:
                resolved_owner = ctx.name_resolver.resolve_identifier(
                    owner,
                    scope_from_context(ctx),
                )
                if resolved_owner.import_line and resolved_owner.kind != "compilation_unit_type":
                    _request_runtime_type_import(
                        resolved_owner.import_line,
                        resolved_owner.kind,
                        ctx,
                    )
                return f"{owner}.{alias}({', '.join(args)})"
        if not _is_type_receiver_segment(owner):
            return None
        qualified_owner = ctx.name_resolver.bindings.file_type_paths.get(owner)
        if qualified_owner is not None and ctx.in_method:
            py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
            return f"{qualified_owner}.{py_method}({', '.join(args)})"
        resolved_owner = ctx.name_resolver.resolve_identifier(owner, scope_from_context(ctx))
        if resolved_owner.is_type_reference and resolved_owner.kind in {
            "imported_type",
            "package_type",
            "compilation_unit_type",
        }:
            if resolved_owner.import_line and resolved_owner.kind != "compilation_unit_type":
                _request_runtime_type_import(
                    resolved_owner.import_line,
                    resolved_owner.kind,
                    ctx,
                )
            py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
            return f"{resolved_owner.python_name}.{py_method}({', '.join(args)})"
    return None


def translate_static_imported_method(
    node: JavaNode,
    *,
    imported_name: str,
    binding: JavaMemberBinding | None = None,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    member_binding = binding or static_import_binding(imported_name, ctx.cfg, kind="method")
    member_binding = _qualify_file_type_owner(member_binding, ctx)
    member_binding = _alias_static_instance_member(member_binding, ctx)
    raw_receiver = member_binding.owner
    method_name = member_binding.member
    result = translate_static_method_invocation(
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
    return static_import_method_fallback(member_binding, args, ctx.cfg)
