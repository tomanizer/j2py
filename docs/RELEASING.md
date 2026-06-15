# Releasing j2py

## PyPI package name

Publish this project as `j2py-converter`.

The import package and console script remain `j2py`, but the `j2py` PyPI distribution
name is already owned by an unrelated Jupyter notebook converter.

## Alpha release checklist

1. Verify the release version in `pyproject.toml` and `j2py/__init__.py`.
2. Move changelog entries from `## Unreleased` to the release heading.
3. Run:

   ```bash
   make release-check
   ```

4. Open and merge the release PR.
5. Create a GitHub release tag, for example `v0.1.0a1`.
6. Confirm PyPI trusted publishing remains configured for:

   - Owner/repository: `tomanizer/j2py`
   - Workflow: `.github/workflows/publish.yml`
   - Environment: `pypi`
   - PyPI project: `j2py-converter`

7. Publish the GitHub release. The `Publish` workflow builds, checks, and uploads the
   wheel/sdist to PyPI.

## Local package checks

`make release-check` runs:

- lock file consistency (`uv lock --check`)
- lint (ruff check + format check)
- strict type check
- normal pytest suite
- future target xfail suite
- Java/Python behavior-equivalence tests
- version consistency (`pyproject.toml` vs `j2py.__version__`)
- import and CLI smoke test
- fresh `dist/` cleanup before building release artifacts
- wheel and sdist build
- sdist hygiene guard that rejects local agent state, caches, corpus clones, reports,
  VS Code build output, VSIX files, and `node_modules`
- `twine check dist/*.whl dist/*.tar.gz`

The publish workflow runs `make release-test` on Python 3.11 and 3.12, then builds
and validates distributions once on Python 3.11.
