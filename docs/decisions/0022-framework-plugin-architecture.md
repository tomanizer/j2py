# ADR 0022 — Framework plugin architecture (Tier 4)

**Date:** 2026-06-17
**Status:** Proposed

## Context

[ADR 0019](0019-annotation-map-framework-lowering.md) added Tier 2 `annotation_map`: a
declarative, strict, project-owned table that lowers a Java annotation to a Python
decorator, base class, init parameter, or comment. It deliberately handles only **1:1**
mappings.

Enterprise frameworks need transforms that a flat table cannot express:

| Scenario | Why `annotation_map` is insufficient |
|---|---|
| `@Configuration` + `@Bean` method pairs | Must correlate members across a class |
| Constructor *and* field `@Autowired` on one class | Init-signature rewriting + field-elision rules |
| `@RequestMapping` class + method composition | Prefix + per-verb path joining |
| JPA `@Entity` + `@Id` + `@Column` + `@OneToMany` | Multi-member ORM graph, not one decorator |
| Cross-class wiring (Controller → Service → Repository) | A dependency graph spanning files |

The Spring → FastAPI/SQLAlchemy cookbook ([#339](https://github.com/tomanizer/j2py/issues/339))
documents exactly these as "manual port required" because Tier 2 cannot reach them (for
example, `@Id`/`@Column` lower to audit comments only; `__tablename__` cannot be emitted as
a class attribute).

Hard-coding Spring/JPA/FastAPI semantics into `j2py/translate/` would violate the PRD
non-goals and bloat the core. j2py core must remain a Java-language transpiler. We need an
extension point so framework lowering lives **outside** core, while reusing the same
emitter pipeline and keeping output auditable.

## Decision

Introduce **Tier 4**: a trusted, opt-in, programmatic plugin extension point.

### Plugin contract (`j2py/framework.py`)

```python
@dataclass(frozen=True)
class InitParam:
    py_name: str
    py_type: str

@dataclass(frozen=True)
class FrameworkTransformResult:
    prefix_lines: tuple[str, ...] = ()       # decorators/comments above the element
    base_classes: tuple[str, ...] = ()       # extra Python bases
    init_params: tuple[InitParam, ...] = ()  # promoted __init__ params
    imports: tuple[str, ...] = ()            # import lines (routed to diagnostics)
    # NOTE: a bare `= MappingProxyType({})` default raises at class-definition time
    # (`ValueError: mutable default mappingproxy ... use default_factory`), so the empty
    # default MUST go through default_factory. Tuple defaults above are immutable and fine.
    metadata: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})  # wiring hints (Phase 2)
    )
    handled: bool = False                    # did this plugin claim the element?

class FrameworkPlugin(ABC):
    """Base class for framework lowering plugins.

    All three hooks have concrete no-op defaults, so a subclass overrides only
    the element kinds it cares about. There are no @abstractmethods: a plugin
    that handles only classes will not crash when the dispatcher calls
    ``transform_field``/``transform_method``.
    """

    name: str = "unnamed"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()

    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()
```

Plugins return **structured results**, never raw file rewrites. A single dispatch module
(`j2py/translate/framework_dispatch.py`) merges results into the existing emitters and is
the only thing the emitter call sites invoke.

#### Why an ABC, not a `Protocol`

The contract is a concrete **abstract base class with no-op default hooks**, not a
`Protocol`. This is a deliberate design choice that removes two bug classes *by
construction* rather than by convention:

- **No pydantic `isinstance` footgun.** `TranslationConfig` carries
  `framework_plugins: list[FrameworkPlugin]`, and pydantic (under
  `arbitrary_types_allowed=True`) builds an `isinstance` validator for that field. A plain
  `Protocol` cannot back `isinstance` and raises `SchemaError: 'cls' must be valid as the
  first argument to 'isinstance'` at model-build time — a guaranteed crash that an author
  must remember to dodge with `@runtime_checkable` (which only checks member *presence*) or
  `list[Any]` (no validation at all). An ABC is `isinstance`-native, so the field validates
  with a real type check and there is no decorator to forget.
- **No "unimplemented hook" crashes.** Because every hook has a concrete no-op default
  (and there are no `@abstractmethod`s), a plugin that overrides only `transform_class`
  cannot raise `NotImplementedError`/`AttributeError` when the dispatcher invokes the other
  two hooks. The "implement only what you need" ergonomics are part of the type, not a
  documentation note.

mypy still enforces hook signatures at plugin-author time via normal subclass type
checking, so the ABC loses none of `Protocol`'s static guarantees.

### `FrameworkContext`, not `TranslationContext`

Plugins receive a narrow, stable `FrameworkContext` — its members are the annotated
`node: JavaNode`, the resolved `element_name`/`element_kind`, the Java→Python name pair,
the annotations with their argument values, the field/param type info, and the
`diagnostics: TranslationDiagnostics` sink (used by the dispatcher for the `warn`/`record`
calls above) — **not** the internal `TranslationContext`. `TranslationContext` is a large
mutable per-translation object (and is not even constructed at the class-decoration call
sites in `classes.py`). Exposing it would freeze core internals as public API and hand
third-party code a mutable surface we cannot safely guarantee. `FrameworkContext` is the
public contract; it can grow additively without churning core.

### Trusted loading: Python config only

Plugins are **never** auto-discovered (no `PYTHONPATH` scan, no entry points in v1). They
are registered exclusively through an explicit trusted Python config:

```python
# j2py_config.py  (loaded only via --config; executes user code)
framework_plugins = [FastApiSpringPlugin()]
```

`TranslationConfig` gains `framework_plugins: list[FrameworkPlugin] = []`
(`arbitrary_types_allowed=True`). Because YAML/TOML cannot express Python objects, the
"trusted code only" property is enforced by construction — no extra guard logic. This
mirrors the existing policy that `.py` configs are trusted code (see
[docs/configuration.md](../configuration.md)).

### Resolution order (per element, short-circuit)

For each class / field / method the dispatcher resolves in order:

1. **Framework plugins**, in registration order. The first plugin returning
   `handled=True` **wins and totally suppresses both later plugins and Tier 2 for that
   element**, preventing duplicate decorators or conflicting bases. Suppression is total:
   results (including `imports` and `metadata`) from non-winning plugins are discarded —
   there is no cross-plugin composition for a single element in v1. Plugins returning
   `handled=False` are treated as no-ops and do not suppress anything.
2. **Tier 2 `annotation_map`** — if no plugin handled the element.
3. **Tier 1 visibility** — diagnostics plus `# @Annotation(...)` audit comments.

### Plugin error handling (single guarded chokepoint)

`transform_*` runs trusted-but-fallible user code, so a hook may raise. The design makes
catching this **structural, not a convention** an implementer can forget:

- Emitters **never call a plugin hook directly.** They call only the `framework_dispatch`
  facade (`resolve_class`/`resolve_field`/`resolve_method`). There is no other code path to
  a plugin.
- Inside the facade, **every** hook is invoked through one private helper —
  `_safe_invoke(plugin, hook_name, ctx)` — which is the sole call site that actually runs
  plugin code. Nothing in the dispatcher calls `plugin.transform_*` outside it.

```python
def _safe_invoke(plugin: FrameworkPlugin, hook: str,
                 ctx: FrameworkContext) -> FrameworkTransformResult:
    try:
        return getattr(plugin, hook)(ctx)
    except Exception as exc:  # trusted code, but never crash a translation run
        ctx.diagnostics.warn(
            ctx.node,
            reason=f"framework plugin {plugin.name!r} raised in {hook}: {exc!r}",
        )
        return FrameworkTransformResult()  # claims nothing -> falls through to Tier 2/1
```

(`TranslationDiagnostics.warn(node, reason=...)` is the existing API; warnings surface for
review and, per ADR 0019's coverage rules, do not reduce `coverage`.)

Because a raised hook returns a `handled=False` result, the resolution order below simply
falls through to Tier 2 then Tier 1 for that element — a broken plugin yields a visible
diagnostic and unmapped-but-correct output, never a hard failure. This matches j2py's
reviewable-degradation ethos. Combined with the ABC's no-op default hooks (which prevent
*missing*-hook errors), the only way a plugin affects an element is by returning a
well-formed result; raising and not-implementing are both absorbed. (A future strict mode
could opt into fail-fast; out of scope for v1.)

A Phase 1 test asserts this contract directly: a deliberately-throwing reference plugin
must produce a diagnostic and Tier-2/Tier-1 output, with the run completing successfully.

### `init_params` aggregation into `__init__`

`transform_field` is invoked per field, but `__init__` is assembled at **class** scope.
The dispatcher therefore aggregates field-level `init_params` up to the class and applies
the **same ordering and dedupe rule Tier 2 uses today**: injected parameters follow the
explicit constructor's parameters (when one exists), in stable Java field-declaration
order, deduplicated by Python parameter name (the existing `seen` set in
`classes._annotation_init_params`). A plugin claiming a field (`handled=True`) supplies
that field's init parameter in place of Tier 2's `field_init_parameter`; it does not get a
second, independent merge path. Plugin authors that also want constructor-param rewriting
beyond appending must emit it via `transform_class` `prefix_lines`/`metadata`, not by
fighting the field aggregator.

### Coverage stays honest

A plugin-handled annotation is recorded as **handled** in `diagnostics.coverage`, the same
as a Tier 2 mapping. Plugins must not be a way to silently inflate or deflate
`TranslationResult.confidence`; the dispatcher accounts for handled nodes centrally.

### Wiring metadata sidecar (Phase 2, opt-in)

A new `emit_wiring_metadata: bool = False` flag makes directory/file translation emit a
per-file `*.wiring.json` aggregating each plugin's `metadata`. j2py core emits metadata
only; generating runnable DI/route bootstrap from it is
[#338 `j2py-wire`](https://github.com/tomanizer/j2py/issues/338), out of scope here.

### Core ships no framework mappings

Core bundles **no** Spring/JPA/Jakarta plugin. A single **reference plugin** built on
*fictional* annotations (`@MappedController`, `@InjectDep`) lives under tests/docs to prove
the contract. A maintained Spring→FastAPI plugin belongs in a separate package
(`j2py-spring-fastapi`), a follow-up.

## Consequences

+ Enterprise users maintain project- or org-local plugins without forking j2py; core PR
  review stays language-focused and framework debates move to plugin repos.
+ Compositional transforms (multi-member ORM, `@Bean` correlation, DI graphs) become
  expressible, closing the cookbook's "manual port" gaps via plugins rather than core.
+ Output remains auditable: plugins add lines/imports/metadata through the existing
  emitters and the existing diagnostics/coverage accounting.
+ The trust and loading model reuses the established `.py`-config policy unchanged.
− Plugins run in-process and are trusted code; a malicious or buggy plugin can emit wrong
  Python or run arbitrary side effects. A hook that *raises* is caught and degraded to a
  diagnostic (see "Plugin error handling"), so it cannot crash a run, but v1 has no
  sandboxing against side effects or wrong output (explicit non-goal), matching today's
  `j2py_config.py` trust model.
− A new public contract (`FrameworkContext`, `FrameworkTransformResult`) must be kept
  stable; that is the cost of the narrow-surface decision and is preferable to exposing
  `TranslationContext`.
− Precedence is plugin-over-Tier-2 per element; a project mixing both must understand the
  short-circuit rule to avoid surprise (documented in `configuration.md`).

## Non-goals

- Auto-discovery / classpath detection of plugins.
- Bundling Spring/Hibernate/Jakarta mappings in core.
- Runnable FastAPI app or DI-container generation from core (that is #338).
- Replacing Tier 2 `annotation_map`; plugins complement it.
- Subprocess / sandbox isolation of plugins (v1 runs in-process like `.py` config today).

## Implementation note (delivery)

Phase 0 is this ADR. Phase 1 (the first implementation PR) ships `j2py/framework.py`, the
`framework_dispatch.py` merge layer, the `framework_plugins` config field, integration at
the four emitter call sites (`classes.py`, `class_fields.py`, `class_methods.py`,
`class_interfaces.py`), and the reference plugin with tests in `make check` (no LLM, no
Spring clone). Phase 2 (wiring sidecar) and Phase 3 (`docs/FRAMEWORK_PLUGINS.md`,
illustrative Spring plugin) are follow-up PRs.

## References

- Issue #337 — Tier 4 framework plugin architecture
- [ADR 0019](0019-annotation-map-framework-lowering.md) — Tier 2 `annotation_map`
- Issue #334 — Tier 1 annotation visibility
- Issue #335 — Tier 2 `annotation_map` config
- Issue #336 — Tier 3 `spring-app-dense` corpus
- Issue #338 — Tier 5 `j2py-wire` wiring generator
- Issue #339 — Spring → FastAPI/SQLAlchemy mapping cookbook
- [docs/configuration.md](../configuration.md)
- [docs/examples/SPRING_MAPPING_COOKBOOK.md](../examples/SPRING_MAPPING_COOKBOOK.md)
