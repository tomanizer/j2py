# 0.7.0 release candidate checklist

This checklist records the package build and clean-environment install verification for
the 0.7.0 release-candidate path. The verification used the current release-candidate
branch state and built artifacts named `0.6.0b1`; the final release PR still needs the
normal version bump to `0.7.0` before tagging.

## Artifact build

Command:

```bash
make release-check
```

Result:

- `uv lock --check` passed.
- Ruff check, ruff format check, and mypy passed.
- Normal pytest passed: `2973 passed, 8 skipped, 105 deselected, 1 xfailed`.
- Future target xfail suite passed with the expected single xfail.
- Behavior corpus passed: `90 passed, 1 deselected`.
- Spring PetClinic smoke passed: `3 passed`.
- Version consistency passed for the current package version: `0.6.0b1`.
- Import and CLI smoke passed.
- Built artifacts:
  - `dist/j2py_converter-0.6.0b1-py3-none-any.whl`
  - `dist/j2py_converter-0.6.0b1.tar.gz`
- Sdist hygiene passed: `dist/j2py_converter-0.6.0b1.tar.gz: clean`.
- `twine check dist/*.whl dist/*.tar.gz` passed for both artifacts.

## Sdist inspection

The sdist contains the expected release-facing source and documentation, including:

- `j2py/`
- `docs/`
- `tests/`
- `packages/j2py-vscode/package.json`
- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE`, `SECURITY.md`, `Makefile`

Focused exclusion check:

```bash
tar -tf dist/j2py_converter-0.6.0b1.tar.gz |
  rg "(__pycache__|\\.pyc|\\.venv|\\.corpus|corpus-reports|node_modules|\\.vsix|tests/fixtures/python)"
```

Result: no matches.

## Clean core install smoke

Commands:

```bash
.venv/bin/python -m venv /private/tmp/j2py-issue-587-core-venv
/private/tmp/j2py-issue-587-core-venv/bin/python -m pip install \
  dist/j2py_converter-0.6.0b1-py3-none-any.whl
```

Installed package location:

```text
/private/tmp/j2py-issue-587-core-venv/lib/python3.11/site-packages/j2py/__init__.py
```

Installed-package smoke results from `/private/tmp`:

- `j2py --help` listed `translate`, `dashboard`, `doctor`, `sarif`, `watch`, `analyze`,
  and `compare`.
- A self-contained `HelloWorld.java` directory translated with `--no-llm --no-validate`
  and produced `/private/tmp/j2py-issue-587-core-smoke/translated_py/demo/HelloWorld.py`.
- `python -m py_compile` passed for the generated `HelloWorld.py`.
- `j2py doctor --json --html` passed on the smoke source: 1 file, 0 parse failures,
  0 semantic warnings, 0 unhandled diagnostics.
- `j2py sarif <doctor.json> --output <doctor.sarif>` passed with 0 SARIF results.

## Clean Spring extra install smoke

Commands:

```bash
.venv/bin/python -m venv /private/tmp/j2py-issue-587-spring-venv
/private/tmp/j2py-issue-587-spring-venv/bin/python -m pip install \
  "dist/j2py_converter-0.6.0b1-py3-none-any.whl[spring]"
```

Installed-package smoke results from `/private/tmp`:

- `j2py-wire --help` listed `list`, `generate`, and `validate`.
- Optional Spring imports passed: `fastapi`, `sqlalchemy`, `httpx`,
  `pydantic_settings`, and `j2py.wire.cli`.
- Installed `j2py translate` with `tests/fixtures/framework/spring_wiring_plugin_config.py`
  translated:
  - `tests/fixtures/java/SpringWiringController.java`
  - `tests/fixtures/java/SpringJdbcConfiguration.java`
  - `tests/fixtures/java/JdbcTemplateSqlAlchemyScaffold.java`
- `j2py-wire list` found 2 wiring sidecars with 11 elements.
- `j2py-wire generate --target fastapi` generated:
  - `wiring/SpringWiringController_wiring.py`
  - `wiring/app_wiring.py`
- `j2py-wire validate --format json` returned warning-only status:
  - `errors`: 0
  - `warnings`: 1
  - warning code: `missing-session-factory`
- `python -m py_compile` passed for the translated Spring files and generated wiring.

The `missing-session-factory` warning is expected: production SQLAlchemy session
lifecycle is project-owned wiring, not a generated j2py runtime policy.

## Optional extras check

The install docs list these extras:

- `yaml`
- `validate`
- `gemini`
- `openai`
- `spring`

The clean Spring install verified the `spring` extra runtime imports. Existing packaging
tests cover the dependency split and default-import boundary in
`tests/packaging/test_pyproject_dependencies.py`.

## Pre-tag checklist

No package-install blocker was found in this verification. Before tagging 0.7.0:

- Bump `pyproject.toml` and `j2py/__init__.py` from the current pre-release version to
  the intended `0.7.0` version.
- Move changelog entries from `Unreleased` to the 0.7.0 heading.
- Refresh these evidence lines if the final version bump changes generated artifact names.
- Run `make release-check` on the release PR.
- Re-run the clean core and Spring-extra install smokes against the final wheel.
- Create the GitHub release tag only after the final release PR is green and merged.
