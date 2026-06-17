"""Switch statement lowering helpers."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_ops import _switch_condition, _switch_label_values
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.statements import translate_body, translate_statement


@dataclass(frozen=True)
class _SwitchPart:
    labels: list[str]
    statements: list[JavaNode]
    is_default: bool
    fallthrough_entry: bool = False


_TERMINAL_SWITCH_STATEMENTS = {
    "break_statement",
    "return_statement",
    "throw_statement",
    "continue_statement",
}


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

    all_case_labels = _switch_case_labels(groups, ctx)
    lines: list[str] = []
    saw_default = False
    after_fallthrough_if = False
    index = 0
    while index < len(groups):
        group = groups[index]
        if is_comment(group):
            ctx.diagnostics.warn(group, reason="preserved comment")
            index += 1
            continue
        if group.type == "switch_block_statement_group":
            collected = _collect_switch_parts(
                groups,
                start_index=index,
                ctx=ctx,
            )
            if collected is None:
                ctx.diagnostics.record(
                    group,
                    supported=False,
                    reason="switch fall-through requires manual translation",
                )
                return [
                    f"{indent}# TODO(j2py): switch fall-through requires manual translation",
                    f"{indent}pass",
                ]
            parts, index = collected
            group_end_index = index - 1
            saw_default_in_parts, after_fallthrough_if = _emit_switch_parts(
                parts,
                subject=subject,
                ctx=ctx,
                indent=indent,
                lines=lines,
                all_case_labels=all_case_labels,
                after_fallthrough_if=after_fallthrough_if,
            )
            saw_default = saw_default or saw_default_in_parts
        elif group.type == "switch_rule":
            translated = _switch_rule_group(group, ctx, indent=indent)
            index += 1
            group_end_index = index - 1
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
            saw_default_in_parts = False
            if labels:
                keyword = "if" if not lines else "elif"
                lines.append(f"{indent}{keyword} {_switch_condition(subject, labels)}:")
            else:
                saw_default = True
                saw_default_in_parts = True
                lines.append(f"{indent}else:")
            lines.extend(body_lines or [f"{indent}    pass"])
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

        if saw_default_in_parts and group_end_index != len(groups) - 1:
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


def _emit_switch_parts(
    parts: list[_SwitchPart],
    *,
    subject: str,
    ctx: TranslationContext,
    indent: str,
    lines: list[str],
    all_case_labels: list[str],
    after_fallthrough_if: bool,
) -> tuple[bool, bool]:
    saw_default_in_parts = False
    pending_fallthrough_if = after_fallthrough_if
    for part in parts:
        if part.is_default:
            saw_default_in_parts = True
            if pending_fallthrough_if:
                lines.append(
                    f"{indent}elif {subject} not in ({', '.join(all_case_labels)}):",
                )
            elif not lines:
                lines.append(f"{indent}if True:")
            else:
                lines.append(f"{indent}else:")
            pending_fallthrough_if = False
        elif part.fallthrough_entry:
            lines.append(f"{indent}if {_switch_condition(subject, part.labels)}:")
            pending_fallthrough_if = True
        else:
            keyword = "if" if not lines else "elif"
            lines.append(f"{indent}{keyword} {_switch_condition(subject, part.labels)}:")
            pending_fallthrough_if = False
        body_lines = _translate_switch_body(part.statements, ctx, indent=indent)
        lines.extend(body_lines or [f"{indent}    pass"])
    return saw_default_in_parts, pending_fallthrough_if


def _switch_case_labels(groups: list[JavaNode], ctx: TranslationContext) -> list[str]:
    labels: list[str] = []
    for group in groups:
        if group.type != "switch_block_statement_group":
            continue
        label = first_child_by_type(group, "switch_label")
        if label is None:
            continue
        label_values = _switch_label_values(label, ctx)
        if label_values:
            labels.extend(label_values)
    return _merge_switch_labels(labels)


def _collect_switch_parts(
    groups: list[JavaNode],
    *,
    start_index: int,
    ctx: TranslationContext,
) -> tuple[list[_SwitchPart], int] | None:
    parts: list[_SwitchPart] = []
    pending_fallthrough: list[str] = []
    index = start_index

    while index < len(groups):
        group = groups[index]
        if is_comment(group):
            index += 1
            continue
        if group.type != "switch_block_statement_group":
            break

        labels, statements, index, is_default = _read_merged_case_group(groups, index, ctx)
        if is_default:
            body = _strip_terminal_break(statements)
            if pending_fallthrough:
                parts.append(
                    _SwitchPart(
                        pending_fallthrough,
                        body,
                        is_default=False,
                        fallthrough_entry=True,
                    ),
                )
            parts.append(_SwitchPart([], body, is_default=True))
            pending_fallthrough = []
            break

        if pending_fallthrough:
            entry_labels = _merge_switch_labels(pending_fallthrough, labels)
            if _statements_fall_through(statements):
                return None
            parts.append(
                _SwitchPart(
                    entry_labels,
                    _strip_terminal_break(statements),
                    is_default=False,
                    fallthrough_entry=True,
                ),
            )
            pending_fallthrough = []
            break

        if _statements_fall_through(statements):
            parts.append(_SwitchPart(labels, statements, is_default=False))
            pending_fallthrough = list(labels)
            continue

        parts.append(_SwitchPart(labels, _strip_terminal_break(statements), is_default=False))
        break

    return parts, index


def _read_merged_case_group(
    groups: list[JavaNode],
    index: int,
    ctx: TranslationContext,
) -> tuple[list[str], list[JavaNode], int, bool]:
    labels: list[str] = []
    statements: list[JavaNode] = []
    saw_default_label = False
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
            break
        label_values = _switch_label_values(label, ctx)
        group_statements = [child for child in group.named_children if child != label]
        meaningful_statements = [
            statement for statement in group_statements if not is_comment(statement)
        ]
        if label_values and not saw_default_label:
            labels.extend(label_values)
        else:
            saw_default_label = True
        statements.extend(group_statements)
        index += 1
        if meaningful_statements:
            break
    return labels, statements, index, saw_default_label


def _statements_fall_through(statements: list[JavaNode]) -> bool:
    terminal_statements = [statement for statement in statements if not is_comment(statement)]
    if not terminal_statements:
        return True
    return terminal_statements[-1].type not in _TERMINAL_SWITCH_STATEMENTS


def _strip_terminal_break(statements: list[JavaNode]) -> list[JavaNode]:
    terminal_statements = [statement for statement in statements if not is_comment(statement)]
    if terminal_statements and terminal_statements[-1].type == "break_statement":
        break_statement = terminal_statements[-1]
        return [statement for statement in statements if statement != break_statement]
    return statements


def _merge_switch_labels(*label_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in label_groups:
        for label in group:
            if label not in seen:
                seen.add(label)
                merged.append(label)
    return merged


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
