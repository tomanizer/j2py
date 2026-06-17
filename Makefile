.PHONY: check lint format typecheck test test-equivalence equivalence-report test-behavior test-targets test-llm-e2e test-llm-gemini-e2e harvest-equivalence harvest-run harvest-gemini harvest-triage harvest-suggest-targets harvest-prune harvest-pipeline harvest-llm test-cov \
	corpus-list-presets corpus-clone-all corpus-hotspots \
	corpus-spring corpus-spring-smoke corpus-spring-update-baseline \
	corpus-spring-dense corpus-spring-dense-check corpus-spring-dense-update-baseline corpus-spring-broad \
	corpus-spring-app-dense corpus-spring-app-dense-check corpus-spring-app-dense-update-baseline \
	corpus-openjdk-java-base \
	corpus-guava-dense corpus-guava-dense-check corpus-guava-dense-update-baseline \
	corpus-commons-lang-dense corpus-commons-lang-dense-check corpus-commons-lang-dense-update-baseline \
	corpus-jackson-dense corpus-jackson-dense-check corpus-jackson-dense-update-baseline \
	corpus-caffeine-dense corpus-caffeine-dense-check corpus-caffeine-dense-update-baseline \
	clean clean-dist ci-local-pr ci-local-governance build sdist-hygiene-check dist-check \
	lock-check version-check import-smoke release-test release-check

CORPUS := uv run python scripts/corpus/translate_corpus.py

# Legacy alias kept for docs/CI that still reference explicit args.
SPRING_DENSE_BASELINE := tests/fixtures/corpus/spring-dense-baseline.json
SPRING_DENSE_ARGS := --preset spring-dense

# ── Primary targets ──────────────────────────────────────────────────────────

check: lint typecheck test  ## Run all checks (alias for ci-local-pr)

lint:  ## Lint with ruff (includes format check)
	uv run --extra dev ruff check j2py/ tests/ scripts/equivalence/
	uv run --extra dev ruff format --check j2py/ tests/ scripts/equivalence/ --exclude tests/fixtures/python

format:  ## Format with ruff
	uv run --extra dev ruff format j2py/ tests/ scripts/equivalence/ --exclude tests/fixtures/python

typecheck:  ## Type-check with mypy (strict)
	uv run --extra dev mypy j2py/

test:  ## Run test suite
	uv run --extra dev pytest -m "not behavior and not live_llm and not target_translation"

test-equivalence:  ## Run runtime equivalence gate (rule-layer translations vs literal-oracle assertions; no JDK, no LLM)
	uv run --extra dev pytest tests/equivalence -m equivalence -v

equivalence-report:  ## Run equivalence gate and print the verified-surface metric table
	mkdir -p corpus-reports
	J2PY_EQUIVALENCE_SURFACE_JSON=corpus-reports/equivalence-surface.json uv run --extra dev pytest tests/equivalence -m equivalence -q
	uv run --extra dev python scripts/equivalence/surface_report.py corpus-reports/equivalence-surface.json

test-behavior:  ## Run Java/Python behavior-equivalence tests (requires a local JDK)
	uv run --extra dev pytest tests/behavior -m behavior

test-targets:  ## Run future Java-to-Python roadmap xfail targets only
	uv run --extra dev pytest tests/targets -m target_translation -rxXs; status=$$?; if [ $$status -eq 5 ]; then exit 0; fi; exit $$status

test-llm-e2e:  ## Run the on-demand live-LLM exploratory test (requires ANTHROPIC_API_KEY)
	@echo "Running live LLM exploratory test. This is excluded from normal make check."
	@if [ -z "$$ANTHROPIC_API_KEY" ] && [ -f .env ]; then \
		set -a; . ./.env; set +a; \
	fi; \
	if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		_key=$$(zsh -lic 'print -r -- $${ANTHROPIC_API_KEY}' 2>/dev/null || true); \
		if [ -n "$$_key" ]; then export ANTHROPIC_API_KEY="$$_key"; fi; \
	fi; \
	if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "ERROR: ANTHROPIC_API_KEY is not visible to make/pytest." >&2; \
		echo "  If the key is in ~/.zshrc, it must be exported:" >&2; \
		echo "    export ANTHROPIC_API_KEY=sk-..." >&2; \
		echo "  Or copy .env.example to .env, or run: source ~/.zshrc" >&2; \
		exit 1; \
	fi; \
	uv run --extra dev pytest -m live_llm tests/llm/test_e2e_llm.py -v -s -rs

test-llm-gemini-e2e:  ## Run the on-demand live Gemini LLM exploratory test (requires GEMINI_API_KEY)
	@echo "Running live Gemini LLM exploratory test. This is excluded from normal make check."
	@if [ -z "$$GEMINI_API_KEY" ] && [ -f .env ]; then \
		set -a; . ./.env; set +a; \
	fi; \
	if [ -z "$$GEMINI_API_KEY" ]; then \
		_key=$$(zsh -lic 'print -r -- $${GEMINI_API_KEY}' 2>/dev/null || true); \
		if [ -n "$$_key" ]; then export GEMINI_API_KEY="$$_key"; fi; \
	fi; \
	if [ -z "$$GEMINI_API_KEY" ]; then \
		echo "ERROR: GEMINI_API_KEY is not visible to make/pytest." >&2; \
		echo "  If the key is in ~/.zshrc, it must be exported:" >&2; \
		echo "    export GEMINI_API_KEY=..." >&2; \
		echo "  Or copy .env.example to .env, or run: source ~/.zshrc" >&2; \
		exit 1; \
	fi; \
	uv run --extra dev pytest -m live_llm tests/llm/test_e2e_llm.py -v -s -rs -k gemini

harvest-llm:  ## Summarize local LLM harvest records for rule-layer triage
	uv run python scripts/harvest/aggregate_llm_harvest.py

harvest-triage: harvest-llm  ## Alias for harvest-llm

harvest-equivalence:  ## Draft literal-oracle pytest from upstream JUnit (TEST_SOURCE=... TARGET_CLASS=... JAVA_FIXTURE=... [WRITE=...])
	uv run --extra dev python scripts/harvest/harvest_equivalence_tests.py \
		--test-source $(TEST_SOURCE) \
		--target-class $(TARGET_CLASS) \
		--java-fixture $(JAVA_FIXTURE) \
		$(if $(WRITE),--write $(WRITE),)

# Prefer checkout .env, then $J2PY_CORPUS_ROOT/.env (git worktrees), then login shell.
LOAD_GEMINI_ENV = \
	if [ -f .env ]; then set -a; . ./.env; set +a; \
	elif [ -n "$$J2PY_CORPUS_ROOT" ] && [ -f "$$J2PY_CORPUS_ROOT/.env" ]; then set -a; . "$$J2PY_CORPUS_ROOT/.env"; set +a; \
	elif [ -z "$$GEMINI_API_KEY" ]; then \
		_key=$$(zsh -lic 'print -r -- $${GEMINI_API_KEY}' 2>/dev/null || true); \
		[ -n "$$_key" ] && export GEMINI_API_KEY="$$_key"; \
	fi

harvest-run:  ## Translate local harvest preset with Gemini and append records (requires GEMINI_API_KEY)
	@$(LOAD_GEMINI_ENV); \
	uv run --extra gemini python scripts/harvest/run_llm_harvest.py --preset local --llm-provider gemini

harvest-gemini:  ## Batch harvest from FILE_LIST queue (Gemini; default LIMIT=10, use LIMIT=2 on free tier)
	@$(LOAD_GEMINI_ENV); \
	uv run --extra gemini python scripts/harvest/run_llm_harvest.py \
		--llm-provider gemini \
		--file-list $(or $(FILE_LIST),.j2py/harvest/queue.txt) \
		--offset $(or $(OFFSET),0) \
		--limit $(or $(LIMIT),10) \
		--sleep-seconds $(or $(SLEEP),6) \
		--skip-temp-paths \
		--skip-package-info

harvest-suggest-targets:  ## Draft FUTURE_TARGETS snippets from coverage-gap harvest records
	uv run python scripts/harvest/suggest_future_targets.py

harvest-prune:  ## Dedupe harvest jsonl (latest row per source; drop resolved)
	uv run python scripts/harvest/prune_llm_harvest.py

harvest-queue:  ## Build/refresh Tier A queue from corpus-reports/ (coverage==1.0, syntax fail)
	uv run python scripts/harvest/build_harvest_queue.py $(if $(REFRESH),--force,)

harvest-promote:  ## Queue + Gemini batch + prune + triage + draft top pattern issues (LIMIT=2)
	@$(LOAD_GEMINI_ENV); \
	uv run --extra gemini python scripts/harvest/run_harvest_promotion.py \
		--limit $(or $(LIMIT),2) \
		--issues $(or $(ISSUES),3)

harvest-promote-issues:  ## Same as harvest-promote but create GitHub issues via gh
	@$(LOAD_GEMINI_ENV); \
	uv run --extra gemini python scripts/harvest/run_harvest_promotion.py \
		--limit $(or $(LIMIT),2) \
		--issues $(or $(ISSUES),3) \
		--create-issues

harvest-promote-dry:  ## Prune, triage, and draft issues only (no LLM calls)
	uv run python scripts/harvest/run_harvest_promotion.py --skip-harvest --skip-local --issues $(or $(ISSUES),3)

harvest-pipeline:  ## Run harvest preset, triage report, and FUTURE_TARGETS draft suggestions
	$(MAKE) harvest-run
	$(MAKE) harvest-triage
	$(MAKE) harvest-suggest-targets
	$(MAKE) harvest-prune

test-cov:  ## Run tests with coverage report
	uv run --extra dev pytest --cov=j2py --cov-report=term-missing --cov-report=xml --cov-fail-under=0
	uv run python scripts/packaging/check_coverage_floor.py coverage.xml --min-line 90

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

corpus-spring:  ## Compare the legacy Spring lexical preset against its committed baseline
	$(CORPUS) --preset spring-lexical --compare-baseline

corpus-spring-smoke:  ## Run a quick 25-file legacy Spring lexical smoke sample
	$(CORPUS) --limit 25

corpus-spring-update-baseline:  ## Regenerate the legacy Spring lexical baseline intentionally
	$(CORPUS) --preset spring-lexical --update-baseline --compare-baseline

corpus-spring-dense:  ## Run spring-dense + construct fixtures without baseline comparison
	$(CORPUS) $(SPRING_DENSE_ARGS)

corpus-spring-dense-check:  ## Compare spring-dense + construct fixtures against its baseline
	$(CORPUS) $(SPRING_DENSE_ARGS) --compare-baseline --fail-on-regression

corpus-spring-dense-update-baseline:  ## Regenerate the spring-dense + construct baseline intentionally
	$(CORPUS) $(SPRING_DENSE_ARGS) --update-baseline

corpus-spring-broad:  ## Exploratory spring-context sample + constructs (no committed baseline)
	$(CORPUS) --preset spring-broad

corpus-spring-app-dense:  ## Run spring-app-dense REST/JPA/transactional samples without baseline comparison
	$(CORPUS) --preset spring-app-dense

corpus-spring-app-dense-check:  ## Compare spring-app-dense against its baseline
	$(CORPUS) --preset spring-app-dense --compare-baseline --fail-on-regression

corpus-spring-app-dense-update-baseline:  ## Regenerate the spring-app-dense baseline intentionally
	$(CORPUS) --preset spring-app-dense --update-baseline

corpus-openjdk-java-base:  ## Exploratory OpenJDK java.base scoreboard sample (external checkout, no baseline)
	$(CORPUS) --preset openjdk-java-base --clone

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
