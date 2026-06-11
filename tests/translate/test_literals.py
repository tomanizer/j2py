"""Literal rule tests."""

from j2py.config.loader import ConfigLoader
from j2py.translate.rules.literals import translate_literal

CFG = ConfigLoader().add_defaults().build()


def test_java_octal_with_leading_separator_translates_to_python_octal() -> None:
    assert translate_literal("0_777", CFG) == "0o777"

