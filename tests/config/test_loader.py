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
llm_provider = "gemini"
model = "gemini-3.5-flash"

[type_map]
LegacyBean = "dict"
""",
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert not cfg.emit_type_hints
    assert cfg.type_map["LegacyBean"] == "dict"
    assert "java.io.Serializable" in cfg.drop_imports
    assert cfg.llm_provider == "gemini"
    assert cfg.model == "gemini-3.5-flash"


def test_config_loader_loads_openai_provider_and_base_url(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text(
        """
llm_provider = "openai-compatible"
llm_base_url = "https://provider.example/v1"
model = "provider-model-id"
""",
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert cfg.llm_provider == "openai"
    assert cfg.llm_base_url == "https://provider.example/v1"
    assert cfg.model == "provider-model-id"


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


def test_config_loader_loads_annotation_map(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    config_file = tmp_path / "j2py.yaml"
    config_file.write_text(
        """
annotation_map:
  RestController:
    python_decorator: mapped_controller
    import: from tests.fixtures.spring_shim import mapped_controller
    preserve_comment: false
  Autowired:
    field_comment: "# injected: {field_type} {field_name}"
    emit_init_param: true
""",
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert cfg.annotation_map["RestController"].python_decorator == "mapped_controller"
    assert (
        cfg.annotation_map["RestController"].import_
        == "from tests.fixtures.spring_shim import mapped_controller"
    )
    assert cfg.annotation_map["RestController"].preserve_comment is False
    assert cfg.annotation_map["Autowired"].emit_init_param is True


def test_config_loader_loads_member_map(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text(
        """
[member_map."com.example.Util.max"]
kind = "method"
python_owner = "Util"
python_member = "max_value"
return_type = "int"

[member_map."com.example.Factory.of"]
kind = "method"
python_owner = "Factory"
python_member = "of"
return_shape = "object:Thing->Thing"
""",
    )

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert cfg.member_map["com.example.Util.max"].kind == "method"
    assert cfg.member_map["com.example.Util.max"].python_member == "max_value"
    assert cfg.member_map["com.example.Util.max"].return_type == "int"
    assert cfg.member_map["com.example.Factory.of"].return_shape == "object:Thing->Thing"


def test_config_loader_rejects_unknown_member_map_entry_key(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text(
        """
[member_map."com.example.Util.max"]
kind = "method"
unknown_behavior = true
""",
    )

    with pytest.raises(ConfigError) as exc_info:
        ConfigLoader().add_defaults().add_file(config_file).build()

    assert "member_map.com.example.Util.max.unknown_behavior" in str(exc_info.value)


@pytest.mark.parametrize(
    ("filename", "content", "requires_yaml"),
    [
        ("j2py_config.py", "emit_wiring_metadata = True\n", False),
        ("j2py.toml", "emit_wiring_metadata = true\n", False),
        ("pyproject.toml", "[tool.j2py]\nemit_wiring_metadata = true\n", False),
        ("j2py.yaml", "emit_wiring_metadata: true\n", True),
    ],
)
def test_config_loader_loads_emit_wiring_metadata_flag(
    tmp_path: Path,
    filename: str,
    content: str,
    requires_yaml: bool,
) -> None:
    if requires_yaml:
        pytest.importorskip("yaml")
    config_file = tmp_path / filename
    config_file.write_text(content)

    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    assert cfg.emit_wiring_metadata is True


def test_config_loader_rejects_unknown_annotation_map_entry_key(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text(
        """
[annotation_map.RestController]
python_decorator = "mapped_controller"
unknown_behavior = true
""",
    )

    with pytest.raises(ConfigError) as exc_info:
        ConfigLoader().add_defaults().add_file(config_file).build()

    message = str(exc_info.value)
    assert "annotation_map.RestController.unknown_behavior" in message


def test_config_loader_rejects_unknown_key_with_suggestion(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text("type_maps = {}\n")

    with pytest.raises(ConfigError) as exc_info:
        ConfigLoader().add_defaults().add_file(config_file).build()

    message = str(exc_info.value)
    assert "Unknown config key: 'type_maps'" in message
    assert "Did you mean 'type_map'?" in message


def test_config_loader_rejects_unknown_llm_provider(tmp_path: Path) -> None:
    config_file = tmp_path / "j2py.toml"
    config_file.write_text('llm_provider = "unknown"\n')

    with pytest.raises(ConfigError) as exc_info:
        ConfigLoader().add_defaults().add_file(config_file).build()

    message = str(exc_info.value)
    assert "llm_provider" in message
    assert "unsupported LLM provider" in message
    assert "anthropic" in message
    assert "gemini" in message
    assert "openai" in message


def test_config_loader_auto_discovers_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.j2py]
target_python = "3.12"
""",
    )

    cfg = ConfigLoader().add_defaults().add_auto_discovered(tmp_path).build()

    assert cfg.target_python == "3.12"


def test_config_loader_auto_discovers_toml(tmp_path: Path) -> None:
    (tmp_path / "j2py.toml").write_text('target_python = "3.12"\n')

    cfg = ConfigLoader().add_defaults().add_auto_discovered(tmp_path).build()

    assert cfg.target_python == "3.12"


def test_config_loader_auto_discovers_yaml(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    (tmp_path / "j2py.yaml").write_text("target_python: '3.12'\n")

    cfg = ConfigLoader().add_defaults().add_auto_discovered(tmp_path).build()

    assert cfg.target_python == "3.12"


def test_config_loader_auto_discovery_ignores_python_config(tmp_path: Path) -> None:
    (tmp_path / "j2py_config.py").write_text(
        "raise RuntimeError('auto-discovered Python config executed')\n",
    )

    cfg = ConfigLoader().add_defaults().add_auto_discovered(tmp_path).build()

    assert cfg.target_python == "3.11"
