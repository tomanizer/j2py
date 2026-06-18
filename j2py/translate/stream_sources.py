"""Stream source-chain and loop-variable helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_field_name


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
        args_node.named_children[0] if args_node is not None and args_node.named_children else None
    )
    if method_name == "stream":
        return receiver, []

    previous = _stream_chain(receiver)
    if previous is None:
        return None
    source, operations = previous
    return source, [*operations, (method_name, arg)]


def _stream_item_name(source: str, ctx: TranslationContext) -> str:
    base = _stream_source_base_name(source)

    # Common collection variable names that are plurals (or singular-looking but used
    # for lists). The previous heuristic turned "status"->"statu", "address"->"addres",
    # "statuses"->"statuse", "classes"->"classe" etc. Use explicit map + safer stripping.
    plural_fixes = {
        "statuses": "status",
        "status": "status",
        "addresses": "address",
        "address": "address",
        "classes": "class",
        "class": "class",  # e.g. List<Class<?>>
        "entries": "entry",
        "interfaces": "interface",
        "boxes": "box",
        "types": "type",
        "cases": "case",
        "values": "value",
    }
    if base in plural_fixes:
        base = plural_fixes[base]
    elif base.endswith("ies") and len(base) > 3:
        base = f"{base[:-3]}y"
    elif base.endswith("es") and len(base) > 2:
        base = base[:-2]
    elif base.endswith("s") and len(base) > 1:
        base = base[:-1]

    if not base or len(base) < 2:
        base = "item"
    name = translate_field_name(base, snake_case=ctx.cfg.snake_case_fields)
    if not name.isidentifier():
        return "item"
    return name


def _stream_source_base_name(source: str) -> str:
    base = source.rsplit(".", 1)[-1].strip()
    while base.endswith("()"):
        base = base[:-2]
    if base.startswith("get_"):
        base = base[4:]
        if "_" in base:
            base = base.rsplit("_", 1)[-1]
    base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)
    return base.strip("_")
