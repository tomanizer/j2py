"""Tests for layered translation configuration."""

from pathlib import Path

import pytest

from j2py.config.loader import ConfigError, ConfigLoader


def test_config_loader_merges_defaults_and_file_overrides(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py_config.py"
    config_file.write_text(
        "\n".join(
            [
                "type_map = {'String': 'Text', 'UUID': 'str'}",
                "drop_imports = {'com.example.Generated'}",
                "target_python = '3.12'",
            ],
        ),
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert cfg.type_map["int"] == "int"
    assert cfg.type_map["String"] == "Text"
    assert cfg.type_map["UUID"] == "str"
    assert "java.lang.String" in cfg.drop_imports
    assert "com.example.Generated" in cfg.drop_imports
    assert cfg.target_python == "3.12"


def test_config_loader_loads_toml_config(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text(
        """
emit_type_hints = false
drop_imports = ["java.io.Serializable"]

[type_map]
LegacyBean = "dict"
""",
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert not cfg.emit_type_hints
    assert cfg.type_map["LegacyBean"] == "dict"
    assert "java.io.Serializable" in cfg.drop_imports


def test_config_loader_loads_pyproject_tool_section(tmp_path: Path) -> None:
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text(
        """
[project]
name = "sample"

[tool.j2py]
snake_case_methods = false
workers = 8

[tool.j2py.import_map]
com.example.MyClass = "from mypackage import MyClass"
""",
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert not cfg.snake_case_methods
    assert cfg.workers == 8
    assert cfg.import_map["com.example.MyClass"] == "from mypackage import MyClass"


def test_config_loader_loads_yaml_config(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    config_file = tmp_path / "j2py.yaml"
    config_file.write_text(
        """
emit_type_hints: true
snake_case_fields: false
type_map:
  MyCustomType: my_module.MyCustomType
drop_annotations:
  - Override
  - SuppressWarnings
""",
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert cfg.type_map["MyCustomType"] == "my_module.MyCustomType"
    assert not cfg.snake_case_fields
    assert "Override" in cfg.drop_annotations


def test_config_loader_rejects_unknown_key_with_suggestion(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text("type_maps = {}\n")

    with pytest.raises(ConfigError) as exc_info:
        ConfigLoader().add_defaults().add_file(config_file).build()

    message = str(exc_info.value)
    assert "Unknown config key: 'type_maps'" in message
    assert "Did you mean 'type_map'?" in message


def test_config_loader_auto_discovers_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.j2py]
target_python = "3.12"
""",
    )

    cfg = ConfigLoader().add_defaults().add_auto_discovered(tmp_path).build()

    assert cfg.target_python == "3.12"
