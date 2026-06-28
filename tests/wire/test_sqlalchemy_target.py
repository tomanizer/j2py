"""Tests for SQLAlchemy persistence wiring generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from j2py.wire.cli import app
from j2py.wire.loader import load_wiring_sidecars
from j2py.wire.targets.common import GENERATED_HEADER
from j2py.wire.targets.sqlalchemy import DB_FILENAME, PERSISTENCE_FILENAME, SQLAlchemyTarget
from j2py.wire.validation import (
    ValidationContext,
    validate_sqlalchemy_wiring,
    validation_exit_code,
)


def test_sqlalchemy_target_generates_importable_persistence_scaffold(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_repository(translated_root)
    _write_persistence_sidecars(translated_root, include_transaction_manager=True)
    _write_sqlalchemy_stub(tmp_path)
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"

    generated = SQLAlchemyTarget(translated_root=translated_root).generate(
        load_result.sidecars,
        output_dir,
    )

    assert generated == [output_dir / DB_FILENAME, output_dir / PERSISTENCE_FILENAME]
    db_source = (output_dir / DB_FILENAME).read_text(encoding="utf-8")
    persistence_source = (output_dir / PERSISTENCE_FILENAME).read_text(encoding="utf-8")
    assert db_source.startswith(GENERATED_HEADER)
    assert "'url': 'app.datasource.url'" in db_source
    assert "'username': 'app.datasource.username'" in db_source
    assert "'transaction_manager'" in db_source
    assert "TODO(j2py): replace DATABASE_URL" in db_source
    assert "TODO(j2py): Spring transaction facts were detected" in db_source
    assert "from sqlalchemy.engine import Connection" in persistence_source
    assert "from owner_repository import OwnerRepository" in persistence_source
    assert "def get_owner_repository(connection: Connection) -> OwnerRepository:" in (
        persistence_source
    )
    assert "repository = OwnerRepository(connection)" in persistence_source
    assert "repository.jdbc_template_connection = connection" in persistence_source

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.syspath_prepend(str(translated_root))
    for name in [
        "sqlalchemy",
        "sqlalchemy.engine",
        "sqlalchemy.orm",
        "wiring.db",
        "wiring.persistence",
        "owner_repository",
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    db_module = __import__("wiring.db", fromlist=["engine", "session_scope"])
    persistence_module = __import__(
        "wiring.persistence",
        fromlist=["get_owner_repository"],
    )
    connection = sys.modules["sqlalchemy.engine"].Connection()
    repository = persistence_module.get_owner_repository(connection)

    assert db_module.engine is not None
    assert repository.jdbc_template is connection
    assert repository.jdbc_template_connection is connection


def test_sqlalchemy_validation_reports_policy_warnings(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_repository(translated_root)
    _write_persistence_sidecars(translated_root, include_transaction_manager=True)
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"
    SQLAlchemyTarget(translated_root=translated_root).generate(load_result.sidecars, output_dir)

    findings = validate_sqlalchemy_wiring(
        ValidationContext(translated_root, output_dir, load_result.sidecars),
    )

    assert {finding.code for finding in findings} == {
        "sqlalchemy-database-policy",
        "sqlalchemy-transaction-policy",
    }
    assert all(finding.severity == "warning" for finding in findings)
    assert validation_exit_code(findings) == 1


def test_fully_qualified_jdbc_constructor_type_is_bound_to_connection(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    translated_root.mkdir(parents=True)
    module = translated_root / "owner_repository.py"
    module.write_text(
        "from __future__ import annotations\n"
        "\n"
        "class OwnerRepository:\n"
        "    def __init__(self, jdbc_template: org.springframework.jdbc.core.JdbcTemplate):\n"
        "        self.jdbc_template = jdbc_template\n"
        "\n"
        "    def rename_owner(self) -> int:\n"
        "        return self.jdbc_template_connection.execute('update owners').rowcount\n",
        encoding="utf-8",
    )
    _write_repository_sidecar(translated_root, module)
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"

    SQLAlchemyTarget(translated_root=translated_root).generate(load_result.sidecars, output_dir)

    source = (output_dir / PERSISTENCE_FILENAME).read_text(encoding="utf-8")
    assert "def get_owner_repository(connection: Connection) -> OwnerRepository:" in source
    assert "repository = OwnerRepository(connection)" in source


def test_directory_output_path_does_not_crash_python_parsing(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    translated_root.mkdir(parents=True)
    output_path = translated_root / "owner_repository.py"
    output_path.mkdir()
    _write_repository_sidecar(translated_root, output_path)
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"

    SQLAlchemyTarget(translated_root=translated_root).generate(load_result.sidecars, output_dir)

    source = (output_dir / PERSISTENCE_FILENAME).read_text(encoding="utf-8")
    assert "def get_owner_repository(connection: Connection) -> OwnerRepository:" in source
    assert "repository = OwnerRepository()" in source


def test_sqlalchemy_validation_reports_missing_placeholder_binding(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_repository(translated_root)
    _write_persistence_sidecars(translated_root, include_transaction_manager=False)
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"
    SQLAlchemyTarget(translated_root=translated_root).generate(load_result.sidecars, output_dir)
    persistence = output_dir / PERSISTENCE_FILENAME
    persistence.write_text(
        persistence.read_text(encoding="utf-8").replace(
            "    repository.jdbc_template_connection = connection\n",
            "",
        ),
        encoding="utf-8",
    )

    findings = validate_sqlalchemy_wiring(
        ValidationContext(translated_root, output_dir, load_result.sidecars),
    )

    assert any(
        finding.code == "sqlalchemy-placeholder-binding" and finding.severity == "error"
        for finding in findings
    )
    assert validation_exit_code(findings) == 2


def test_sqlalchemy_validation_reports_missing_generated_files(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_repository(translated_root)
    _write_persistence_sidecars(translated_root, include_transaction_manager=False)
    load_result = load_wiring_sidecars(translated_root)

    findings = validate_sqlalchemy_wiring(
        ValidationContext(translated_root, tmp_path / "wiring", load_result.sidecars),
    )

    assert {finding.code for finding in findings} == {"orphan-sqlalchemy-persistence"}
    assert len(findings) == 2
    assert all(finding.severity == "error" for finding in findings)


def test_j2py_wire_generate_sqlalchemy_cli_target(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_repository(translated_root)
    _write_persistence_sidecars(translated_root, include_transaction_manager=False)
    output_dir = tmp_path / "wiring"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["generate", str(translated_root), "--target", "sqlalchemy", "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert f"generated {output_dir / DB_FILENAME}" in result.output
    assert f"generated {output_dir / PERSISTENCE_FILENAME}" in result.output


def _write_translated_repository(translated_root: Path) -> None:
    translated_root.mkdir(parents=True, exist_ok=True)
    (translated_root / "owner_repository.py").write_text(
        "from __future__ import annotations\n"
        "\n"
        "class JdbcTemplate:\n"
        "    pass\n"
        "\n"
        "class OwnerRepository:\n"
        "    def __init__(self, jdbc_template: JdbcTemplate) -> None:\n"
        "        self.jdbc_template = jdbc_template\n"
        "\n"
        "    def rename_owner(self) -> int:\n"
        "        return self.jdbc_template_connection.execute('update owners').rowcount\n",
        encoding="utf-8",
    )


def _write_persistence_sidecars(
    translated_root: Path,
    *,
    include_transaction_manager: bool,
) -> None:
    module = translated_root / "owner_repository.py"
    elements = [
        _jdbc_bean_element(
            "dataSource",
            "data_source",
            "DataSource",
            properties={
                "url": "app.datasource.url",
                "username": "app.datasource.username",
            },
        ),
        _jdbc_bean_element(
            "jdbcTemplate",
            "jdbc_template",
            "JdbcTemplate",
            dependencies=["data_source"],
        ),
        _class_element("OwnerRepository", role="repository", component_name="ownerRepository"),
    ]
    if include_transaction_manager:
        elements.insert(
            2,
            _jdbc_bean_element(
                "transactionManager",
                "transaction_manager",
                "PlatformTransactionManager",
                dependencies=["data_source"],
                constructor_type="DataSourceTransactionManager",
            ),
        )
    (translated_root / "owner_repository.wiring.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "OwnerRepository.java",
                "output": str(module),
                "elements": elements,
            },
        ),
        encoding="utf-8",
    )


def _write_repository_sidecar(translated_root: Path, module: Path) -> None:
    (translated_root / "owner_repository.wiring.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "OwnerRepository.java",
                "output": str(module),
                "elements": [
                    _class_element(
                        "OwnerRepository",
                        role="repository",
                        component_name="ownerRepository",
                    ),
                ],
            },
        ),
        encoding="utf-8",
    )


def _class_element(
    class_name: str,
    *,
    role: str,
    component_name: str,
) -> dict[str, object]:
    return {
        "plugin": "spring-wiring",
        "kind": "class",
        "java_name": class_name,
        "python_name": class_name,
        "annotations": [],
        "metadata": {
            "spring": {
                "profile_version": 1,
                "role": role,
                "component_name": component_name,
            },
        },
    }


def _jdbc_bean_element(
    java_name: str,
    python_name: str,
    python_type: str,
    *,
    properties: dict[str, str] | None = None,
    dependencies: list[str] | None = None,
    constructor_type: str | None = None,
) -> dict[str, object]:
    dependency_records = [
        {
            "name": dependency,
            "java_name": dependency,
            "type": "DataSource",
            "java_type": "DataSource",
            "source": "parameter",
        }
        for dependency in dependencies or []
    ]
    constructor_args = []
    if constructor_type is not None:
        constructor_args.append(
            {
                "type": constructor_type,
                "arguments": [{"kind": "identifier", "value": "data_source"}],
            },
        )
    jdbc_bean = {
        "name": java_name,
        "java_name": java_name,
        "python_name": python_name,
        "java_type": python_type,
        "python_type": python_type,
        "properties": [
            {"target": target, "key": key} for target, key in (properties or {}).items()
        ],
        "dependencies": dependency_records,
        "constructor_args": constructor_args,
        "method_calls": [],
        "source_location": {"line": 1},
    }
    return {
        "plugin": "spring-wiring",
        "kind": "method",
        "java_name": java_name,
        "python_name": python_name,
        "annotations": [],
        "metadata": {
            "spring": {
                "profile_version": 1,
                "jdbc_bean": jdbc_bean,
                "bean": {
                    **jdbc_bean,
                    "qualifier": None,
                    "primary": False,
                    "lazy": None,
                    "init_method": "",
                    "destroy_method": "",
                    "factory_methods": [],
                    "unsupported": [],
                },
            },
        },
    }


def _write_sqlalchemy_stub(root: Path) -> None:
    sqlalchemy = root / "sqlalchemy"
    sqlalchemy.mkdir()
    (sqlalchemy / "__init__.py").write_text(
        "from .engine import Engine\n\ndef create_engine(*args, **kwargs):\n    return Engine()\n",
        encoding="utf-8",
    )
    (sqlalchemy / "engine.py").write_text(
        "class Connection:\n"
        "    pass\n"
        "\n"
        "class _Begin:\n"
        "    def __enter__(self):\n"
        "        return Connection()\n"
        "    def __exit__(self, exc_type, exc, tb):\n"
        "        return False\n"
        "\n"
        "class Engine:\n"
        "    def begin(self):\n"
        "        return _Begin()\n",
        encoding="utf-8",
    )
    (sqlalchemy / "orm.py").write_text(
        "class Session:\n"
        "    def commit(self):\n"
        "        pass\n"
        "    def rollback(self):\n"
        "        pass\n"
        "    def close(self):\n"
        "        pass\n"
        "\n"
        "class sessionmaker:\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        pass\n"
        "    def __call__(self):\n"
        "        return Session()\n",
        encoding="utf-8",
    )
