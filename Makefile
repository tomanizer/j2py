.PHONY: check lint format typecheck test test-behavior test-targets test-llm-e2e test-cov \
	corpus-list-presets corpus-clone-all \
	corpus-spring corpus-spring-smoke corpus-spring-update-baseline \
	corpus-spring-dense corpus-spring-dense-check corpus-spring-dense-update-baseline corpus-spring-broad \
	corpus-guava-dense corpus-guava-dense-check corpus-guava-dense-update-baseline \
	corpus-commons-lang-dense corpus-commons-lang-dense-check corpus-commons-lang-dense-update-baseline \
	corpus-jackson-dense corpus-jackson-dense-check corpus-jackson-dense-update-baseline \
	corpus-caffeine-dense corpus-caffeine-dense-check corpus-caffeine-dense-update-baseline \
	clean ci-local-pr ci-local-governance build dist-check release-check

CORPUS := uv run python scripts/corpus/translate_spring_sample.py

# Legacy alias kept for docs/CI that still reference explicit args.
SPRING_DENSE_BASELINE := tests/fixtures/corpus/spring-dense-baseline.json
SPRING_DENSE_ARGS := --preset spring-dense

# ── Primary targets ──────────────────────────────────────────────────────────

check: lint typecheck test  ## Run all checks (alias for ci-local-pr)

lint:  ## Lint with ruff
	uv run --extra dev ruff check j2py/ tests/

format:  ## Format with ruff
	uv run --extra dev ruff format j2py/ tests/

typecheck:  ## Type-check with mypy (strict)
	uv run --extra dev mypy j2py/

test:  ## Run test suite
	uv run --extra dev pytest -m "not behavior and not live_llm"

test-behavior:  ## Run Java/Python behavior-equivalence tests (requires a local JDK)
	uv run --extra dev pytest tests/behavior -m behavior

test-targets:  ## Run future Java-to-Python roadmap xfail targets only
	uv run --extra dev pytest tests/targets -m target_translation -rxXs; status=$$?; if [ $$status -eq 5 ]; then exit 0; fi; exit $$status

test-llm-e2e:  ## Run the on-demand live-LLM exploratory test (requires ANTHROPIC_API_KEY)
	@echo "Running live LLM exploratory test. This is excluded from normal make check."
	uv run --extra dev pytest -m live_llm tests/llm/test_e2e_llm.py -v -s

test-cov:  ## Run tests with coverage report
	uv run --extra dev pytest --cov=j2py --cov-report=term-missing --cov-report=xml

corpus-list-presets:  ## List pinned external Java corpus presets
	$(CORPUS) --list-presets

corpus-clone-all:  ## Clone or refresh all pinned corpus preset checkouts under .corpus/
	@for preset in $$(PYTHONPATH=scripts/corpus uv run python -c "from corpus_presets import CLONE_PRESET_NAMES; print(' '.join(CLONE_PRESET_NAMES))"); do \
		echo "=== $$preset ==="; \
		$(CORPUS) --preset $$preset --clone --limit 1 || exit $$?; \
	done
	@echo "Done. Checkouts are under .corpus/ (or \$$J2PY_CORPUS_ROOT/.corpus/ when set)."

corpus-spring:  ## Compare the Spring corpus sample against the committed baseline
	$(CORPUS) --preset spring-lexical --compare-baseline

corpus-spring-smoke:  ## Run a quick 25-file Spring corpus smoke sample without baseline comparison
	$(CORPUS) --limit 25

corpus-spring-update-baseline:  ## Regenerate the committed Spring corpus baseline intentionally
	$(CORPUS) --preset spring-lexical --update-baseline --compare-baseline

corpus-spring-dense:  ## Run the preferred dense Spring + curated-construct corpus without comparing the baseline
	$(CORPUS) $(SPRING_DENSE_ARGS)

corpus-spring-dense-check:  ## Compare the preferred dense Spring + curated-construct corpus against its baseline
	$(CORPUS) $(SPRING_DENSE_ARGS) --compare-baseline --fail-on-regression

corpus-spring-dense-update-baseline:  ## Regenerate the preferred dense Spring + curated-construct corpus baseline intentionally
	$(CORPUS) $(SPRING_DENSE_ARGS) --update-baseline

corpus-spring-broad:  ## Broader spring-context sample plus construct fixtures (no baseline compare)
	$(CORPUS) --preset spring-broad

corpus-guava-dense:  ## Run the Guava dense corpus without baseline comparison
	$(CORPUS) --preset guava-dense

corpus-guava-dense-check:  ## Compare Guava dense corpus against its baseline
	$(CORPUS) --preset guava-dense --compare-baseline --fail-on-regression

corpus-guava-dense-update-baseline:  ## Regenerate the Guava dense corpus baseline intentionally
	$(CORPUS) --preset guava-dense --update-baseline

corpus-commons-lang-dense:  ## Run the Commons Lang dense corpus without baseline comparison
	$(CORPUS) --preset commons-lang-dense

corpus-commons-lang-dense-check:  ## Compare Commons Lang dense corpus against its baseline
	$(CORPUS) --preset commons-lang-dense --compare-baseline --fail-on-regression

corpus-commons-lang-dense-update-baseline:  ## Regenerate the Commons Lang dense corpus baseline intentionally
	$(CORPUS) --preset commons-lang-dense --update-baseline

corpus-jackson-dense:  ## Run the Jackson databind dense corpus without baseline comparison
	$(CORPUS) --preset jackson-dense

corpus-jackson-dense-check:  ## Compare Jackson databind dense corpus against its baseline
	$(CORPUS) --preset jackson-dense --compare-baseline --fail-on-regression

corpus-jackson-dense-update-baseline:  ## Regenerate the Jackson databind dense corpus baseline intentionally
	$(CORPUS) --preset jackson-dense --update-baseline

corpus-caffeine-dense:  ## Run the Caffeine dense corpus without baseline comparison
	$(CORPUS) --preset caffeine-dense

corpus-caffeine-dense-check:  ## Compare Caffeine dense corpus against its baseline
	$(CORPUS) --preset caffeine-dense --compare-baseline --fail-on-regression

corpus-caffeine-dense-update-baseline:  ## Regenerate the Caffeine dense corpus baseline intentionally
	$(CORPUS) --preset caffeine-dense --update-baseline

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

dist-check: build  ## Validate built distributions with twine
	uv run --extra dev twine check dist/*.whl dist/*.tar.gz

release-check: check test-targets test-behavior dist-check  ## Run alpha release readiness checks
