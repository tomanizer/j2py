"""Tests for layered translation configuration."""

from pathlib import Path

from j2py.config.loader import ConfigLoader


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
