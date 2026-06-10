.PHONY: check lint format typecheck test test-cov clean ci-local-pr ci-local-governance

# ── Primary targets ──────────────────────────────────────────────────────────

check: lint typecheck test  ## Run all checks (alias for ci-local-pr)

lint:  ## Lint with ruff
	uv run ruff check j2py/ tests/

format:  ## Format with ruff
	uv run ruff format j2py/ tests/

typecheck:  ## Type-check with mypy (strict)
	uv run mypy j2py/

test:  ## Run test suite
	uv run pytest

test-cov:  ## Run tests with coverage report
	uv run pytest --cov=j2py --cov-report=term-missing --cov-report=xml

# ── CI local presets ─────────────────────────────────────────────────────────
# These mirror exactly what GitHub Actions runs. If make ci-local-pr passes,
# CI will pass.

ci-local-pr: check  ## For code/test/docs PRs — lint + typecheck + test

ci-local-governance: check  ## For CI/tooling/dependency PRs — same gates, explicit label

# ── Utility ──────────────────────────────────────────────────────────────────

clean:  ## Remove build artifacts and caches
	rm -rf dist/ .mypy_cache/ .ruff_cache/ .pytest_cache/ htmlcov/ coverage.xml
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +

build:  ## Build wheel and sdist
	uv build
