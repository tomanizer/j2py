"""Tests for Java type → Python type translation."""

import pytest

from j2py.config.loader import ConfigLoader
from j2py.translate.rules.types import (
    element_type_from_container,
    is_api_get_receiver_type,
    is_map_like_type,
    is_var_type,
    translate_type,
)

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
    ("MultiValueMap<String, String>", "dict[str, str]"),
    ("Properties", "dict"),
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


@pytest.mark.parametrize(
    ("py_type", "expected"),
    [
        ("dict[str, int]", True),
        ("MultiValueMap[str, str]", True),
        ("ListMultimap[str, str]", True),
        ("Multimap[str, str]", True),
        ("AnnotationAttributes", True),
        ("AnnotationAttributes | None", True),
        ("list[str]", False),
        ("object", False),
    ],
)
def test_is_map_like_type(py_type: str, expected: bool) -> None:
    assert is_map_like_type(py_type) is expected


@pytest.mark.parametrize(
    ("py_type", "expected"),
    [
        ("list[str]", True),
        ("ImmutableList[str]", True),
        ("ArrayList[str]", True),
        ("dict[str, int]", False),
    ],
)
def test_is_list_like_type(py_type: str, expected: bool) -> None:
    from j2py.translate.rules.types import is_list_like_type

    assert is_list_like_type(py_type) is expected


@pytest.mark.parametrize(
    ("py_type", "expected"),
    [
        ("Field", True),
        ("BeanPropertyWriter", True),
        ("java.lang.reflect.Field", True),
        ("ScheduledFuture", True),
        ("Future", True),
        ("ScheduledFuture | None", True),
        ("dict[str, int]", False),
        ("HashMap", False),
    ],
)
def test_is_api_get_receiver_type(py_type: str, expected: bool) -> None:
    assert is_api_get_receiver_type(py_type) is expected
