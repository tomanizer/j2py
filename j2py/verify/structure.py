"""Structural verification for translated Python output."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field

from j2py.analyze.symbols import ClassSymbol, FileSymbols
from j2py.translate.rules.naming import translate_class_name, translate_method_name


@dataclass
class StructuralVerificationResult:
    """Result of checking translated Python shape against Java symbols."""

    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def verify_structure(symbols: FileSymbols, python_source: str) -> StructuralVerificationResult:
    """Check that translated Python preserves Java class and method presence/order."""
    try:
        module = ast.parse(python_source)
    except SyntaxError as exc:
        return StructuralVerificationResult(errors=[f"Structural verification skipped: {exc}"])

    errors: list[str] = []
    _verify_classes(
        expected=symbols.classes,
        actual=[node for node in module.body if isinstance(node, ast.ClassDef)],
        errors=errors,
        owner="module",
    )
    return StructuralVerificationResult(errors=errors)


def _verify_classes(
    *,
    expected: list[ClassSymbol],
    actual: list[ast.ClassDef],
    errors: list[str],
    owner: str,
) -> None:
    expected_names = [translate_class_name(cls.name) for cls in expected]
    actual_names = [node.name for node in actual]

    for name in _missing_names(expected_names, actual_names):
        errors.append(f"Missing class in {owner}: {name}")

    if not _preserves_order(expected_names, actual_names):
        errors.append(
            f"Class order changed in {owner}: expected {expected_names}, got {actual_names}",
        )

    actual_by_name = {node.name: node for node in actual}
    for cls in expected:
        py_class = actual_by_name.get(translate_class_name(cls.name))
        if py_class is None:
            continue
        _verify_methods(cls, py_class, errors)
        nested = [node for node in py_class.body if isinstance(node, ast.ClassDef)]
        _verify_classes(
            expected=cls.inner_classes,
            actual=nested,
            errors=errors,
            owner=f"class {translate_class_name(cls.name)}",
        )


def _verify_methods(cls: ClassSymbol, py_class: ast.ClassDef, errors: list[str]) -> None:
    expected = [_python_method_name(cls, method.name) for method in cls.methods]
    actual = [
        node.name
        for node in py_class.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]

    for name in _missing_names(expected, actual):
        errors.append(f"Missing method in class {translate_class_name(cls.name)}: {name}")

    if not _preserves_order(expected, actual):
        errors.append(
            "Method order changed in class "
            f"{translate_class_name(cls.name)}: expected {expected}, got {actual}",
        )


def _python_method_name(cls: ClassSymbol, java_name: str) -> str:
    if java_name == cls.name:
        return "__init__"
    return translate_method_name(java_name)


def _missing_names(expected: list[str], actual: list[str]) -> list[str]:
    missing: list[str] = []
    actual_counts = Counter(actual)
    for name, count in Counter(expected).items():
        deficit = count - actual_counts[name]
        missing.extend([name] * max(deficit, 0))
    return missing


def _preserves_order(expected: list[str], actual: list[str]) -> bool:
    position = 0
    for name in expected:
        try:
            position = actual.index(name, position) + 1
        except ValueError:
            return False
    return True
