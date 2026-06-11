"""Tests for Java type → Python type translation."""

import pytest

from j2py.config.loader import ConfigLoader
from j2py.translate.rules.types import element_type_from_container, is_var_type, translate_type

cfg = ConfigLoader().add_defaults().build()


@pytest.mark.parametrize("java, expected", [
    ("int", "int"),
    ("boolean", "bool"),
    ("String", "str"),
    ("void", "None"),
    ("double", "float"),
    ("long", "int"),
    ("Object", "object"),
    ("Class<?>", "type[Any]"),
    ("Function<TypeName, @Nullable CodeBlock>", "Function[TypeName, CodeBlock]"),
    ("List<String>", "list[str]"),
    ("Map<String, Integer>", "dict[str, int]"),
    ("Optional<String>", "str | None"),
    ("int[]", "list[int]"),
    ("List<Map<String, Integer>>", "list[dict[str, int]]"),
    ("?", "Any"),
])
def test_translate_type(java: str, expected: str):
    assert translate_type(java, cfg) == expected


@pytest.mark.parametrize(
    ("java_type", "expected"),
    [
        ("var", True),
        ("  var  ", True),
        ("List<String>", False),
    ],
)
def test_is_var_type(java_type: str, expected: bool) -> None:
    assert is_var_type(java_type) is expected


@pytest.mark.parametrize(
    ("container", "expected"),
    [
        ("list[str]", "str"),
        ("list[dict[str, object]]", "dict[str, object]"),
        ("dict[str, int]", "str"),
        ("str", None),
    ],
)
def test_element_type_from_container(container: str, expected: str | None) -> None:
    assert element_type_from_container(container) == expected
