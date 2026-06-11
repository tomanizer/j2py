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

- lint
- strict type check
- normal pytest suite
- future target xfail suite
- Java/Python behavior-equivalence tests
- wheel and sdist build
- `twine check dist/*`
