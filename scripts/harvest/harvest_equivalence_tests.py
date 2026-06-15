#!/usr/bin/env python3
"""Harvest Phase 1 literal-oracle equivalence tests from Java test sources."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import JavaNode, ParsedFile, parse_file
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.literals import translate_literal, translate_string_literal
from j2py.translate.rules.naming import camel_to_snake, safe_identifier, translate_method_name

SUPPORTED_ASSERTIONS = {
    "assertEquals",
    "assertFalse",
    "assertNotNull",
    "assertNull",
    "assertTrue",
}

LITERAL_NODE_TYPES = {
    "binary_integer_literal",
    "character_literal",
    "decimal_floating_point_literal",
    "decimal_integer_literal",
    "false",
    "hex_floating_point_literal",
    "hex_integer_literal",
    "null_literal",
    "octal_integer_literal",
    "string_literal",
    "true",
}

_CFG = ConfigLoader().add_defaults().build()
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EQUIVALENCE_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "equivalence"


@dataclass(frozen=True)
class HarvestedAssertion:
    test_name: str
    line: int
    python_assertion: str


@dataclass(frozen=True)
class SkippedAssertion:
    line: int
    assertion: str
    reason: str
    source: str


@dataclass(frozen=True)
class HarvestResult:
    test_source: Path
    target_class: str
    java_fixture: str
    harvested: tuple[HarvestedAssertion, ...]
    skipped: tuple[SkippedAssertion, ...]

    @property
    def harvested_count(self) -> int:
        return len(self.harvested)

    @property
    def dropped_expression_oracle_count(self) -> int:
        return sum(1 for item in self.skipped if item.reason == "expression-oracle expected value")

    @property
    def unsupported_assertion_count(self) -> int:
        return sum(1 for item in self.skipped if item.reason == "unsupported assertion")

    @property
    def skipped_method_count(self) -> int:
        return sum(
            1
            for item in self.skipped
            if item.reason
            in {
                "target method not in fixture",
                "overloaded target method",
                "unsafe unqualified target call",
                "unsupported target call",
            }
        )


@dataclass(frozen=True)
class HarvestContext:
    target_class: str
    target_fqn: str
    static_imported_methods: frozenset[str]
    declared_methods: frozenset[str]
    overloaded_methods: frozenset[str]


def harvest_file(test_source: Path, *, target_class: str, java_fixture: str) -> HarvestResult:
    """Return literal-oracle assertions harvested from ``test_source``."""
    parsed = _parse_file_checked(test_source)
    context = _build_context(
        parsed,
        target_class=target_class,
        java_fixture=java_fixture,
    )
    harvested: list[HarvestedAssertion] = []
    skipped: list[SkippedAssertion] = []
    seen_assertions: set[tuple[int, int]] = set()
    used_test_names: dict[str, int] = {}

    for method in parsed.root.find_all("method_declaration"):
        if not _is_test_method(method):
            continue
        test_name = _dedupe_test_name(_test_method_name(method), used_test_names)
        for invocation in method.find_all("method_invocation"):
            key = (invocation.location.line, invocation.location.column)
            if key in seen_assertions:
                continue
            assertion_name = _method_invocation_name(invocation)
            if assertion_name is None or not assertion_name.startswith("assert"):
                continue
            seen_assertions.add(key)
            if assertion_name not in SUPPORTED_ASSERTIONS:
                skipped.append(
                    _skip(invocation, assertion_name, "unsupported assertion"),
                )
                continue
            harvested_assertion, skipped_assertion = _translate_assertion(
                invocation,
                assertion_name=assertion_name,
                test_name=test_name,
                context=context,
            )
            if harvested_assertion is not None:
                harvested.append(harvested_assertion)
            if skipped_assertion is not None:
                skipped.append(skipped_assertion)

    return HarvestResult(
        test_source=test_source,
        target_class=target_class,
        java_fixture=java_fixture,
        harvested=tuple(harvested),
        skipped=tuple(skipped),
    )


def render_pytest_draft(result: HarvestResult) -> str:
    """Render a reviewable pytest draft for harvested assertions."""
    fixture_var = _fixture_var_name(result.target_class)
    source_var = f"{fixture_var}_source"
    module_name = f"_{result.target_class}_harvest"

    lines = [
        f'"""Draft equivalence tests harvested from {result.test_source.name}.',
        "",
        "Review before committing. This file was generated from Phase 1 literal-oracle",
        "assertions only; skipped assertions are summarized at the bottom.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import sys",
        "",
        "import pytest",
        "",
        "from tests.equivalence.harness import (",
        "    install_fixture_stubs,",
        "    load_translated_module,",
        "    translate_rule_layer,",
        ")",
        "",
        f'JAVA_CLASS = "{result.java_fixture}"',
        "",
        "pytestmark = pytest.mark.equivalence",
        "",
        "",
        '@pytest.fixture(scope="module")',
        f"def {source_var}() -> str:",
        "    return translate_rule_layer(JAVA_CLASS)",
        "",
        "",
        '@pytest.fixture(scope="module")',
        f"def {fixture_var}({source_var}: str):",
        "    stub_modules = install_fixture_stubs(JAVA_CLASS)",
        "    try:",
        f'        module = load_translated_module({source_var}, "{module_name}")',
        f"        yield module.{result.target_class}",
        "    finally:",
        f'        sys.modules.pop("{module_name}", None)',
        "        for name in reversed(stub_modules):",
        "            sys.modules.pop(name, None)",
        "",
    ]

    by_test = _group_harvested_assertions(result.harvested)
    if by_test:
        for test_name, assertions in by_test.items():
            lines.extend(["", f"def {test_name}({fixture_var}) -> None:"])
            for assertion in assertions:
                source_ref = f"{result.test_source.name}:{assertion.line}"
                lines.append(f"    {assertion.python_assertion}  # {source_ref}")
    else:
        lines.extend(
            [
                "",
                '@pytest.mark.skip(reason="no Phase 1 literal-oracle assertions harvested")',
                f"def test_no_harvested_assertions({fixture_var}) -> None:",
                f"    assert {fixture_var} is not None",
            ]
        )

    lines.extend(
        [
            "",
            "",
            "# Harvest summary",
            f"# harvested assertions: {result.harvested_count}",
            f"# dropped expression-oracle assertions: {result.dropped_expression_oracle_count}",
            f"# unsupported assertions: {result.unsupported_assertion_count}",
            f"# skipped target calls: {result.skipped_method_count}",
        ]
    )
    for skipped in result.skipped:
        lines.append(
            f"# skipped {result.test_source.name}:{skipped.line} "
            f"{skipped.assertion} - {skipped.reason}: {skipped.source}"
        )
    lines.append("")
    return "\n".join(lines)


def _group_harvested_assertions(
    assertions: Iterable[HarvestedAssertion],
) -> dict[str, list[HarvestedAssertion]]:
    grouped: dict[str, list[HarvestedAssertion]] = {}
    for assertion in assertions:
        grouped.setdefault(assertion.test_name, []).append(assertion)
    return grouped


def _dedupe_test_name(test_name: str, used_test_names: dict[str, int]) -> str:
    used_test_names[test_name] = used_test_names.get(test_name, 0) + 1
    suffix = used_test_names[test_name]
    return test_name if suffix == 1 else f"{test_name}_{suffix}"


def _parse_file_checked(path: Path) -> ParsedFile:
    parsed = parse_file(path)
    if parsed.has_errors:
        locations = ", ".join(
            f"{error.type}@{error.location.line}:{error.location.column}" for error in parsed.errors
        )
        raise ValueError(f"Cannot harvest from Java source with parse errors: {path} ({locations})")
    return parsed


def _build_context(parsed: ParsedFile, *, target_class: str, java_fixture: str) -> HarvestContext:
    fixture = _parse_file_checked(_resolve_java_fixture(java_fixture))
    target_fqn = _target_class_fqn(fixture, target_class=target_class)
    static_imported_methods = _target_static_imports(
        parsed,
        target_fqn=target_fqn,
    )
    return HarvestContext(
        target_class=target_class,
        target_fqn=target_fqn,
        static_imported_methods=frozenset(static_imported_methods),
        declared_methods=frozenset(_declared_methods(fixture, target_class=target_class)),
        overloaded_methods=frozenset(_overloaded_methods(fixture, target_class=target_class)),
    )


def _resolve_java_fixture(java_fixture: str) -> Path:
    path = Path(java_fixture)
    if path.is_file():
        return path
    fixture_path = _EQUIVALENCE_FIXTURES / java_fixture
    if fixture_path.is_file():
        return fixture_path
    raise FileNotFoundError(f"Java fixture not found: {java_fixture}")


def _target_class_fqn(parsed: ParsedFile, *, target_class: str) -> str:
    if _target_class_node(parsed.root, target_class=target_class) is None:
        raise ValueError(f"Target class {target_class!r} not found in {parsed.path}")
    package_node = first_child_by_type(parsed.root, "package_declaration")
    if package_node is None:
        return target_class
    package_name = first_child_by_type(package_node, "identifier", "scoped_identifier")
    if package_name is None:
        return target_class
    return f"{package_name.text}.{target_class}"


def _target_static_imports(parsed: ParsedFile, *, target_fqn: str) -> set[str]:
    methods: set[str] = set()
    for import_node in parsed.root.find_all("import_declaration"):
        if not any(child.text == "static" for child in import_node.children):
            continue
        named = import_node.named_children
        if any(child.type == "asterisk" for child in named):
            continue
        imported = next((child.text for child in named if child.type == "scoped_identifier"), "")
        prefix = f"{target_fqn}."
        if imported.startswith(prefix):
            methods.add(imported.rsplit(".", 1)[-1])
    return methods


def _overloaded_methods(parsed: ParsedFile, *, target_class: str) -> set[str]:
    counts = Counter(_direct_target_method_names(parsed, target_class=target_class))
    return {name for name, count in counts.items() if count > 1}


def _declared_methods(parsed: ParsedFile, *, target_class: str) -> set[str]:
    return set(_direct_target_method_names(parsed, target_class=target_class))


def _direct_target_method_names(parsed: ParsedFile, *, target_class: str) -> list[str]:
    target_class_node = _target_class_node(parsed.root, target_class=target_class)
    if target_class_node is None:
        return []
    class_body = first_child_by_type(target_class_node, "class_body")
    if class_body is None:
        return []
    return [
        name
        for method in class_body.named_children
        if method.type == "method_declaration"
        if _is_static_method_declaration(method)
        if (name := _method_declaration_name(method)) is not None
    ]


def _is_static_method_declaration(method: JavaNode) -> bool:
    modifiers = first_child_by_type(method, "modifiers")
    return modifiers is not None and any(child.text == "static" for child in modifiers.children)


def _target_class_node(root: JavaNode, *, target_class: str) -> JavaNode | None:
    for class_node in root.find_all("class_declaration", "interface_declaration"):
        name_node = class_node.child_by_field("name") or first_child_by_type(
            class_node, "identifier", "type_identifier"
        )
        if name_node is not None and name_node.text == target_class:
            return class_node
    return None


def _method_declaration_name(method: JavaNode) -> str | None:
    name_node = method.child_by_field("name") or first_child_by_type(method, "identifier")
    return name_node.text if name_node is not None else None


def _is_test_method(method: JavaNode) -> bool:
    name_node = method.child_by_field("name") or first_child_by_type(method, "identifier")
    if name_node is not None and name_node.text.startswith("test"):
        return True
    modifiers = first_child_by_type(method, "modifiers")
    return modifiers is not None and "@Test" in modifiers.text


def _test_method_name(method: JavaNode) -> str:
    name_node = method.child_by_field("name") or first_child_by_type(method, "identifier")
    raw_name = name_node.text if name_node is not None else f"line_{method.location.line}"
    translated = translate_method_name(raw_name)
    return translated if translated.startswith("test_") else f"test_{translated}"


def _translate_assertion(
    invocation: JavaNode,
    *,
    assertion_name: str,
    test_name: str,
    context: HarvestContext,
) -> tuple[HarvestedAssertion | None, SkippedAssertion | None]:
    args = _assertion_args(invocation)
    if assertion_name == "assertEquals":
        args = _drop_optional_message_arg(args, expected_arg_count=2)
        if len(args) != 2:
            return None, _skip(invocation, assertion_name, "unsupported assertion arity")
        expected, actual = args
        expected_py = _literal_to_python(expected)
        if expected_py is None:
            return None, _skip(invocation, assertion_name, "expression-oracle expected value")
        actual_py, skip_reason = _target_call_to_python(actual, context=context)
        if actual_py is None:
            return None, _skip(invocation, assertion_name, skip_reason or "unsupported target call")
        return (
            HarvestedAssertion(
                test_name=test_name,
                line=invocation.location.line,
                python_assertion=f"assert {actual_py} == {expected_py}",
            ),
            None,
        )

    args = _drop_optional_message_arg(args, expected_arg_count=1)
    if len(args) != 1:
        return None, _skip(invocation, assertion_name, "unsupported assertion arity")
    actual_py, skip_reason = _target_call_to_python(args[0], context=context)
    if actual_py is None:
        return None, _skip(invocation, assertion_name, skip_reason or "unsupported target call")
    if assertion_name == "assertTrue":
        assertion = f"assert {actual_py} is True"
    elif assertion_name == "assertFalse":
        assertion = f"assert {actual_py} is False"
    elif assertion_name == "assertNull":
        assertion = f"assert {actual_py} is None"
    elif assertion_name == "assertNotNull":
        assertion = f"assert {actual_py} is not None"
    else:
        return None, _skip(invocation, assertion_name, "unsupported assertion")
    return (
        HarvestedAssertion(
            test_name=test_name,
            line=invocation.location.line,
            python_assertion=assertion,
        ),
        None,
    )


def _assertion_args(invocation: JavaNode) -> list[JavaNode]:
    args_node = invocation.child_by_field("arguments") or first_child_by_type(
        invocation, "argument_list"
    )
    if args_node is None:
        return []
    return list(args_node.named_children)


def _drop_optional_message_arg(args: list[JavaNode], *, expected_arg_count: int) -> list[JavaNode]:
    if len(args) == expected_arg_count + 1 and args[0].type == "string_literal":
        return args[1:]
    return args


def _method_invocation_name(invocation: JavaNode) -> str | None:
    args_node = invocation.child_by_field("arguments") or first_child_by_type(
        invocation, "argument_list"
    )
    for child in reversed(invocation.named_children):
        if args_node is not None and child.node == args_node.node:
            continue
        if child.type == "identifier":
            return child.text
    return None


def _target_call_to_python(
    node: JavaNode, *, context: HarvestContext
) -> tuple[str | None, str | None]:
    if node.type != "method_invocation":
        return None, "unsupported target call"
    args_node = node.child_by_field("arguments") or first_child_by_type(node, "argument_list")
    if args_node is None:
        return None, "unsupported target call"
    identifiers = [
        child.text
        for child in node.named_children
        if child.type == "identifier" and child.node != args_node.node
    ]
    if len(identifiers) == 2:
        receiver, method_name = identifiers
        if receiver != context.target_class:
            return None, "unsupported target call"
    elif len(identifiers) == 1:
        method_name = identifiers[0]
        if method_name not in context.static_imported_methods:
            return None, "unsafe unqualified target call"
    else:
        return None, "unsupported target call"

    if method_name not in context.declared_methods:
        return None, "target method not in fixture"

    if method_name in context.overloaded_methods:
        return None, "overloaded target method"

    rendered_args: list[str] = []
    for arg in args_node.named_children:
        rendered = _literal_to_python(arg)
        if rendered is None:
            return None, "unsupported target call"
        rendered_args.append(rendered)

    fixture_var = _fixture_var_name(context.target_class)
    method = translate_method_name(method_name)
    return f"{fixture_var}.{method}({', '.join(rendered_args)})", None


def _fixture_var_name(target_class: str) -> str:
    return safe_identifier(camel_to_snake(target_class))


def _literal_to_python(node: JavaNode) -> str | None:
    if node.type == "string_literal":
        return translate_string_literal(node.text)
    if node.type == "null_literal":
        return "None"
    if node.type in {"true", "false"}:
        return translate_literal(node.text, _CFG)
    if node.type == "unary_expression":
        children = node.children
        if len(children) == 2 and children[0].text in {"-", "+"}:
            literal = _literal_to_python(children[1])
            return f"{children[0].text}{literal}" if literal is not None else None
        return None
    if node.type in LITERAL_NODE_TYPES:
        return translate_literal(node.text, _CFG)
    return None


def _skip(invocation: JavaNode, assertion_name: str, reason: str) -> SkippedAssertion:
    return SkippedAssertion(
        line=invocation.location.line,
        assertion=assertion_name,
        reason=reason,
        source=" ".join(invocation.text.split()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-source", type=Path, required=True, help="Java test source file")
    parser.add_argument("--target-class", required=True, help="Java class under test")
    parser.add_argument(
        "--java-fixture",
        required=True,
        help="Vendored Java fixture filename passed to translate_rule_layer()",
    )
    parser.add_argument("--write", type=Path, default=None, help="Write the pytest draft to a file")
    args = parser.parse_args()

    result = harvest_file(
        args.test_source,
        target_class=args.target_class,
        java_fixture=args.java_fixture,
    )
    draft = render_pytest_draft(result)
    if args.write is None:
        print(draft)
    else:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(draft, encoding="utf-8")
        print(f"Wrote {args.write}")
        print(
            "Harvest summary: "
            f"{result.harvested_count} harvested, "
            f"{result.dropped_expression_oracle_count} expression-oracle dropped, "
            f"{result.unsupported_assertion_count} unsupported assertions, "
            f"{result.skipped_method_count} skipped target calls"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
