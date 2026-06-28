"""Tests for Pydantic Settings wiring generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from j2py.wire.cli import app
from j2py.wire.loader import load_wiring_sidecars
from j2py.wire.targets.common import GENERATED_HEADER
from j2py.wire.targets.pydantic_settings import (
    SETTINGS_FILENAME,
    PydanticSettingsTarget,
    field_name_for_property_key,
)
from j2py.wire.validation import (
    ValidationContext,
    validate_pydantic_settings_wiring,
    validation_exit_code,
)


def test_pydantic_settings_target_generates_importable_settings_scaffold(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    translated_root = tmp_path / "translated"
    _write_settings_sidecar(
        translated_root,
        {
            "url": "app.datasource.url",
            "username": "app.datasource.username",
            "driverClassName": "app.datasource.driver-class-name",
        },
    )
    _write_pydantic_stubs(tmp_path)
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"

    generated = PydanticSettingsTarget(translated_root=translated_root).generate(
        load_result.sidecars,
        output_dir,
    )

    assert generated == [output_dir / SETTINGS_FILENAME]
    source = (output_dir / SETTINGS_FILENAME).read_text(encoding="utf-8")
    assert source.startswith(GENERATED_HEADER)
    assert "from pydantic import Field" in source
    assert "from pydantic_settings import BaseSettings, SettingsConfigDict" in source
    assert "'app_datasource_url': 'app.datasource.url'" in source
    assert "app_datasource_url: str | None = Field(" in source
    assert "validation_alias='app.datasource.url'" in source
    assert "app_datasource_driver_class_name: str | None = Field(" in source
    assert "# Source: AppConfig.java::dataSource.url" in source
    assert "TODO(j2py): decide project environment variable names" in source

    findings = validate_pydantic_settings_wiring(
        ValidationContext(translated_root, output_dir, load_result.sidecars),
    )
    assert findings == []
    assert validation_exit_code(findings) == 0

    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ["pydantic", "pydantic_settings", "wiring.settings"]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    settings_module = __import__("wiring.settings", fromlist=["ApplicationSettings"])

    assert settings_module.settings is not None
    assert settings_module.SOURCE_PROPERTY_KEYS["app_datasource_url"] == "app.datasource.url"


def test_pydantic_settings_target_is_deterministic(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_settings_sidecar(
        translated_root,
        {
            "username": "app.datasource.username",
            "url": "app.datasource.url",
        },
    )
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"
    target = PydanticSettingsTarget(translated_root=translated_root)

    target.generate(load_result.sidecars, output_dir)
    first = (output_dir / SETTINGS_FILENAME).read_text(encoding="utf-8")
    target.generate(load_result.sidecars, output_dir)
    second = (output_dir / SETTINGS_FILENAME).read_text(encoding="utf-8")

    assert second == first


def test_pydantic_settings_validation_reports_missing_generated_file(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_settings_sidecar(translated_root, {"url": "app.datasource.url"})
    load_result = load_wiring_sidecars(translated_root)

    findings = validate_pydantic_settings_wiring(
        ValidationContext(translated_root, tmp_path / "wiring", load_result.sidecars),
    )

    assert {finding.code for finding in findings} == {"orphan-pydantic-settings"}
    assert all(finding.severity == "error" for finding in findings)
    assert validation_exit_code(findings) == 2


def test_pydantic_settings_validation_reports_duplicate_and_colliding_keys(
    tmp_path: Path,
) -> None:
    translated_root = tmp_path / "translated"
    _write_settings_sidecar(
        translated_root,
        {
            "url": "app.datasource.url",
            "jdbcUrl": "app.datasource.url",
            "driverClassName": "app.datasource.driver-class-name",
            "driverClassNameAlias": "app.datasource.driver_class_name",
        },
    )
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"
    PydanticSettingsTarget(translated_root=translated_root).generate(
        load_result.sidecars,
        output_dir,
    )

    findings = validate_pydantic_settings_wiring(
        ValidationContext(translated_root, output_dir, load_result.sidecars),
    )

    assert [finding.code for finding in findings] == [
        "pydantic-settings-property-conflict",
        "pydantic-settings-property-conflict",
    ]
    assert any("recorded multiple times" in finding.message for finding in findings)
    assert any("maps multiple Spring property keys" in finding.message for finding in findings)
    assert validation_exit_code(findings) == 2


def test_j2py_wire_generate_pydantic_settings_cli_target(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_settings_sidecar(translated_root, {"url": "app.datasource.url"})
    output_dir = tmp_path / "wiring"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate",
            str(translated_root),
            "--target",
            "pydantic-settings",
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert f"generated {output_dir / SETTINGS_FILENAME}" in result.output


def test_field_name_for_property_key_is_stable_and_safe() -> None:
    assert field_name_for_property_key("app.datasource.driver-class-name") == (
        "app_datasource_driver_class_name"
    )
    assert field_name_for_property_key("1.invalid-key") == "setting_1_invalid_key"
    assert field_name_for_property_key("class") == "class_"


def _write_settings_sidecar(translated_root: Path, properties: dict[str, str]) -> None:
    translated_root.mkdir(parents=True, exist_ok=True)
    module = translated_root / "app_config.py"
    module.write_text("class AppConfig:\n    pass\n", encoding="utf-8")
    (translated_root / "app_config.wiring.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "AppConfig.java",
                "output": str(module),
                "elements": [
                    {
                        "plugin": "spring-wiring",
                        "kind": "method",
                        "java_name": "dataSource",
                        "python_name": "data_source",
                        "annotations": [],
                        "metadata": {
                            "spring": {
                                "profile_version": 1,
                                "jdbc_bean": {
                                    "name": "dataSource",
                                    "java_name": "dataSource",
                                    "python_name": "data_source",
                                    "java_type": "DataSource",
                                    "python_type": "DataSource",
                                    "properties": [
                                        {"target": target, "key": key}
                                        for target, key in properties.items()
                                    ],
                                    "dependencies": [],
                                    "constructor_args": [],
                                    "method_calls": [],
                                    "source_location": {"line": 12},
                                },
                            },
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )


def _write_pydantic_stubs(root: Path) -> None:
    (root / "pydantic.py").write_text(
        "def Field(default=None, **kwargs):\n    return default\n",
        encoding="utf-8",
    )
    (root / "pydantic_settings.py").write_text(
        "class BaseSettings:\n"
        "    def __init__(self, **kwargs):\n"
        "        for key, value in kwargs.items():\n"
        "            setattr(self, key, value)\n"
        "\n"
        "class SettingsConfigDict(dict):\n"
        "    pass\n",
        encoding="utf-8",
    )
