.PHONY: check lint format typecheck test test-equivalence test-behavior test-targets test-llm-e2e test-cov \
	corpus-list-presets corpus-clone-all corpus-hotspots \
	corpus-spring corpus-spring-smoke corpus-spring-update-baseline \
	corpus-spring-dense corpus-spring-dense-check corpus-spring-dense-update-baseline corpus-spring-broad \
	corpus-guava-dense corpus-guava-dense-check corpus-guava-dense-update-baseline \
	corpus-commons-lang-dense corpus-commons-lang-dense-check corpus-commons-lang-dense-update-baseline \
	corpus-jackson-dense corpus-jackson-dense-check corpus-jackson-dense-update-baseline \
	corpus-caffeine-dense corpus-caffeine-dense-check corpus-caffeine-dense-update-baseline \
	clean clean-dist ci-local-pr ci-local-governance build sdist-hygiene-check dist-check \
	lock-check version-check import-smoke release-test release-check

CORPUS := uv run python scripts/corpus/translate_spring_sample.py

# Legacy alias kept for docs/CI that still reference explicit args.
SPRING_DENSE_BASELINE := tests/fixtures/corpus/spring-dense-baseline.json
SPRING_DENSE_ARGS := --preset spring-dense

# ── Primary targets ──────────────────────────────────────────────────────────

check: lint typecheck test  ## Run all checks (alias for ci-local-pr)

lint:  ## Lint with ruff (includes format check)
	uv run --extra dev ruff check j2py/ tests/
	uv run --extra dev ruff format --check j2py/ tests/ --exclude tests/fixtures/python

format:  ## Format with ruff
	uv run --extra dev ruff format j2py/ tests/ --exclude tests/fixtures/python

typecheck:  ## Type-check with mypy (strict)
	uv run --extra dev mypy j2py/

test:  ## Run test suite
	uv run --extra dev pytest -m "not behavior and not live_llm"

test-equivalence:  ## Run runtime equivalence gate (rule-layer translations vs literal-oracle assertions; no JDK, no LLM)
	uv run --extra dev pytest tests/equivalence -m equivalence -v

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

corpus-hotspots:  ## Rank cross-corpus unhandled/syntax gaps from committed baselines
	uv run python scripts/corpus/aggregate_hotspots.py

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

corpus-spring-dense:  ## Run spring-dense + construct fixtures without baseline comparison
	$(CORPUS) $(SPRING_DENSE_ARGS)

corpus-spring-dense-check:  ## Compare spring-dense + construct fixtures against its baseline (CI gate)
	$(CORPUS) $(SPRING_DENSE_ARGS) --compare-baseline --fail-on-regression

corpus-spring-dense-update-baseline:  ## Regenerate the spring-dense + construct baseline intentionally
	$(CORPUS) $(SPRING_DENSE_ARGS) --update-baseline

corpus-spring-broad:  ## Exploratory spring-context sample + constructs (no committed baseline)
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

clean: clean-dist  ## Remove build artifacts and caches
	rm -rf .mypy_cache*/ .ruff_cache*/ .pytest_cache*/ htmlcov/ .coverage coverage.xml corpus-reports/
	find . -type d -name '__pycache__*' -not -path './.venv/*' -exec rm -rf {} +

clean-dist:  ## Remove release distribution artifacts
	rm -rf dist/

build: clean-dist  ## Build wheel and sdist from a fresh dist/ directory
	uv build

sdist-hygiene-check: build  ## Fail if source distributions contain local/generated state
	uv run python scripts/packaging/check_sdist_hygiene.py dist/*.tar.gz

dist-check: build sdist-hygiene-check  ## Validate built distributions with twine
	uv run --extra dev twine check dist/*.whl dist/*.tar.gz

lock-check:  ## Fail when uv.lock is out of date with pyproject.toml
	uv lock --check

version-check:  ## Fail when pyproject.toml and j2py.__version__ disagree
	uv run python scripts/packaging/check_release_versions.py

import-smoke:  ## Verify core imports and CLI entry point
	uv run python -c "import j2py; import j2py.parse.java_ast; import j2py.translate.rules.types"
	uv run j2py --help > /dev/null

release-test: lock-check check test-targets test-behavior version-check import-smoke  ## Release tests without building dist

release-check: release-test dist-check  ## Run alpha release readiness checks
