"""Literal rule tests."""

from j2py.config.loader import ConfigLoader
from j2py.translate.rules.literals import java_string_literal_value, translate_literal

CFG = ConfigLoader().add_defaults().build()


def test_java_octal_with_leading_separator_translates_to_python_octal() -> None:
    assert translate_literal("0_777", CFG) == "0o777"
    assert translate_literal("0_", CFG) == "0o0"


def test_java_text_block_value_strips_incidental_indent_and_decodes_escapes() -> None:
    token = '"""\n        alpha\\s\n        beta\\\n        gamma\n        """'

    assert java_string_literal_value(token) == "alpha \nbetagamma\n"
