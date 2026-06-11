.PHONY: check lint format typecheck test test-behavior test-targets test-llm-e2e test-cov corpus-spring corpus-spring-smoke corpus-spring-update-baseline clean ci-local-pr ci-local-governance

# ── Primary targets ──────────────────────────────────────────────────────────

check: lint typecheck test  ## Run all checks (alias for ci-local-pr)

lint:  ## Lint with ruff
	uv run ruff check j2py/ tests/

format:  ## Format with ruff
	uv run ruff format j2py/ tests/

typecheck:  ## Type-check with mypy (strict)
	uv run mypy j2py/

test:  ## Run test suite
	uv run pytest -m "not behavior and not live_llm"

test-behavior:  ## Run Java/Python behavior-equivalence tests (requires a local JDK)
	uv run pytest tests/behavior -m behavior

test-targets:  ## Run future Java-to-Python roadmap xfail targets only
	uv run pytest tests/targets -m target_translation -rxXs

test-llm-e2e:  ## Run the on-demand live-LLM exploratory test (requires ANTHROPIC_API_KEY)
	@echo "Running live LLM exploratory test. This is excluded from normal make check."
	uv run pytest -m live_llm tests/llm/test_e2e_llm.py -v -s

test-cov:  ## Run tests with coverage report
	uv run pytest --cov=j2py --cov-report=term-missing --cov-report=xml

corpus-spring:  ## Compare the Spring corpus sample against the committed baseline
	uv run python scripts/corpus/translate_spring_sample.py --compare-baseline

corpus-spring-smoke:  ## Run a quick 25-file Spring corpus smoke sample without baseline comparison
	uv run python scripts/corpus/translate_spring_sample.py --limit 25

corpus-spring-update-baseline:  ## Regenerate the committed Spring corpus baseline intentionally
	uv run python scripts/corpus/translate_spring_sample.py --update-baseline --compare-baseline

corpus-spring-dense:  ## Density-based selection of minimal-size but construct-rich files (prefers high node-type diversity per LOC)
	# Note: does not compare to the default baseline (different sampling parameters)
	uv run python scripts/corpus/translate_spring_sample.py --strategy density --max-loc 250 --min-constructs 5

corpus-spring-broad:  ## Broader + more extensive sample (more modules + curated construct files for the new roadmap items)
	# Note: does not compare to the default baseline (different sampling parameters)
	uv run python scripts/corpus/translate_spring_sample.py \
		--module spring-context/src/main/java \
		--include-constructs \
		--limit 150 \
		--strategy density

# ── CI local presets ─────────────────────────────────────────────────────────
# These mirror exactly what GitHub Actions runs. If make ci-local-pr passes,
# CI will pass.

ci-local-pr: check  ## For code/test/docs PRs — lint + typecheck + test

ci-local-governance: check  ## For CI/tooling/dependency PRs — same gates, explicit label

# ── Utility ──────────────────────────────────────────────────────────────────

clean:  ## Remove build artifacts and caches
	rm -rf dist/ .mypy_cache/ .ruff_cache/ .pytest_cache/ htmlcov/ .coverage coverage.xml corpus-reports/
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +

build:  ## Build wheel and sdist
	uv build
