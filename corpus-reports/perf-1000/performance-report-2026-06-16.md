# j2py Corpus Performance Report - 1000-file preset runs

Date: 2026-06-16

Scope: six committed dense corpus presets were run with `--limit 1000`. The run did
not compare against committed baselines because those baselines use the preset default
sample sizes. Wall time was captured with `/usr/bin/time -p`.

Command shape:

```bash
uv run python scripts/corpus/translate_corpus.py \
  --preset <preset> \
  --limit 1000 \
  --json-out corpus-reports/perf-1000/<preset>-1000.json \
  --csv-out corpus-reports/perf-1000/<preset>-1000.csv
```

Note: `--limit 1000` is an upper bound. Presets with fewer eligible files after module,
LOC, construct-density, annotation, and exclude-path filters scanned fewer than 1000
files.

## Summary

| Preset | Requested | Scanned | Wall s | Files/s | Parse | Syntax | Avg coverage | Full coverage | Unhandled files | <80% cov |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `spring-dense` | 1000 | 1000 | 46.75 | 21.39 | 99.70% | 99.60% | 99.85% | 959 | 41 | 2 |
| `spring-app-dense` | 1000 | 389 | 22.21 | 17.51 | 99.74% | 98.46% | 99.22% | 331 | 58 | 2 |
| `guava-dense` | 1000 | 255 | 18.64 | 13.68 | 98.82% | 99.22% | 98.27% | 159 | 96 | 3 |
| `commons-lang-dense` | 1000 | 208 | 13.79 | 15.08 | 100.00% | 99.04% | 98.50% | 187 | 21 | 6 |
| `jackson-dense` | 1000 | 420 | 32.48 | 12.93 | 100.00% | 92.86% | 99.41% | 371 | 49 | 4 |
| `caffeine-dense` | 1000 | 43 | 4.08 | 10.54 | 100.00% | 100.00% | 99.45% | 28 | 15 | 0 |

Overall:

- Total scanned: 2,315 files
- Total wall time: 137.95 seconds
- Overall throughput: 16.78 files/s
- Weighted parse success: 99.70%
- Weighted generated-Python syntax success: 98.10%
- Weighted average skeleton coverage: 99.36%
- Full-coverage files: 2,035
- Files with unhandled constructs: 280
- Files below 80% coverage: 17

## Enterprise and annotation measures

| Preset | Method body files | Method body rate | Annotation-only stubs | Stub rate | Annotation warning files | Warning file rate | Total annotation warnings | Avg warnings/file | Total annotation uses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `spring-dense` | 825 | 82.50% | 25 | 2.50% | 818 | 81.80% | 4,341 | 4.34 | 230 |
| `spring-app-dense` | 279 | 71.72% | 95 | 24.42% | 352 | 90.49% | 2,898 | 7.45 | 1,374 |
| `guava-dense` | 219 | 85.88% | 0 | 0.00% | 254 | 99.61% | 5,429 | 21.29 | 0 |
| `commons-lang-dense` | 180 | 86.54% | 0 | 0.00% | 173 | 83.17% | 768 | 3.69 | 0 |
| `jackson-dense` | 384 | 91.43% | 0 | 0.00% | 354 | 84.29% | 3,426 | 8.16 | 0 |
| `caffeine-dense` | 37 | 86.05% | 0 | 0.00% | 41 | 95.35% | 475 | 11.05 | 0 |

Annotation-warning counts are semantic warnings from the rule layer, not coverage
failures. They are still useful because they show where generated Python may need a
framework annotation map, import map, or manual semantic review even when node coverage
and syntax are high.

## Highest-signal gaps

| Preset | Top unhandled reasons | Syntax failure samples |
|---|---|---|
| `spring-dense` | ambiguous `get` receiver type (30); overloaded `append` dispatch (9); overloaded `sort` dispatch (6); overloaded `determine_types` dispatch (4); switch rule block yield (3) | `DefaultNamingPolicy.java`, `MimeTypeUtils.java`, `YamlProcessor.java`, `InstanceSupplierCodeGenerator.java` |
| `spring-app-dense` | unknown AssertJ `assertThat` static import (48); ambiguous `get` receiver type (33); unknown Mockito `mock` static import (14); unknown AssertJ exception assertion import (8); unknown BDDMockito `given` import (5) | `FragmentRenderingStreamTests.java`, `EnableTransactionManagementIntegrationTests.java`, `WebMvcConfigurationSupportTests.java`, `RequestMappingHandlerAdapterTests.java` |
| `guava-dense` | unknown `CollectPreconditions.checkNonnegative` static import (19); ambiguous `get` receiver type (19); overloaded `copy_of` dispatch (14); overloaded `of` dispatch (13); unknown `Maps.immutableEntry` static import (10) | `CollectCollectors.java`, `ArrayTable.java` |
| `commons-lang-dense` | overloaded `append` dispatch (41); overloaded `__init__` dispatch (11); numeric division type certainty (10); overloaded `to_string` dispatch (9); overloaded `random` dispatch (8) | `AnnotationUtils.java`, `StrMatcher.java` |
| `jackson-dense` | overloaded `number_node` dispatch (28); ambiguous `get` receiver type (16); unsupported statement block (8); unsized array allocation handling (8); numeric division type certainty (6) | `LRUMap.java`, `PropertyBindingException.java`, `AnnotatedFieldCollector.java`, `MapProperty.java` |
| `caffeine-dense` | unknown Caffeine static imports: `ceilingPowerOfTwo` (4), `requireArgument` (3), `calculateHashMapCapacity` (3), `UNSET_INT` (2); unknown `Locale.US` static import (3) | none |

## Interpretation

The 1000-file stress run confirms that current dense-corpus breadth is high: all
presets stayed above 98% average rule-layer coverage, and four of six presets stayed at
or above 99% generated-Python syntax success. The main outlier is `jackson-dense`, where
syntax success drops to 92.86% despite 99.41% average coverage, so its failures are more
about invalid emitted Python than broad unhandled-node coverage.

The recurring implementation themes are stable across libraries:

- Static import lowering remains the broadest deterministic gap for app/test-heavy and
  utility-heavy Java.
- Overloaded method dispatch remains visible in Commons Lang, Guava, Spring, and
  Jackson.
- Ambiguous collection `get` lowering is still cross-corpus.
- Annotation warning volume is highest in Guava by count and Caffeine by per-file rate,
  even though neither preset has source-level annotation uses in the selected files; that
  points to broader semantic-warning noise that should be separated from real framework
  annotation lowering work.
- `spring-app-dense` is the main annotation-stub risk: 95 annotation-only stubs, or
  24.42% of the scanned files.
- Jackson has the highest syntax-risk cluster and should be prioritized for generated
  Python parseability.

## Artifacts

- `corpus-reports/perf-1000/spring-dense-1000.json`
- `corpus-reports/perf-1000/spring-app-dense-1000.json`
- `corpus-reports/perf-1000/guava-dense-1000.json`
- `corpus-reports/perf-1000/commons-lang-dense-1000.json`
- `corpus-reports/perf-1000/jackson-dense-1000.json`
- `corpus-reports/perf-1000/caffeine-dense-1000.json`
- Matching per-file CSVs are in the same directory.

## Harness note

The first Jackson run exposed a corpus-report serialization bug: unhandled diagnostic
reasons containing semicolons broke summary parsing. The harness now escapes semicolons
in counter keys and parses old counter strings defensively.
