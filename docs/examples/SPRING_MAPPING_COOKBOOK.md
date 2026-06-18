# Spring → FastAPI/SQLAlchemy mapping cookbook

Reference mappings for lowering the most common Spring application-layer patterns to a
**FastAPI + SQLAlchemy** Python stack. This is a **guide and fixture spec**, not full
Spring support in j2py core.

j2py enables **no** Spring, FastAPI, JPA, or DI semantics by default
([ADR 0019](../decisions/0019-annotation-map-framework-lowering.md)). The core package
does include `annotation_map_preset: spring` for no-op Spring marker decorators; the
FastAPI/SQLAlchemy profile in this cookbook remains project policy realized through the
tiers below.

| Tier | Mechanism | Status | Issue |
|---|---|---|---|
| Tier 1 | Default lowering + audit comments | shipped | — |
| Tier 2 | `annotation_map` config | shipped | [#335](https://github.com/tomanizer/j2py/issues/335) |
| Tier 4 | Framework plugins (richer transforms) | planned | [#337](https://github.com/tomanizer/j2py/issues/337) |
| Tier 5 | `j2py-wire` (DI/route bootstrap) | planned | [#338](https://github.com/tomanizer/j2py/issues/338) |

Related: [#333](https://github.com/tomanizer/j2py/issues/333) (enterprise audit),
[#334](https://github.com/tomanizer/j2py/issues/334) (annotation visibility),
[#339](https://github.com/tomanizer/j2py/issues/339) (this cookbook).

## How to reproduce the output below

Each "after" block reproduces the **actual** j2py output for the matching fixture under
[`tests/fixtures/corpus/spring-app/`](../../tests/fixtures/corpus/spring-app/), translated
with the reference map — abridged for readability: the leading
`from __future__ import annotations`, class docstrings, and repeated methods (shown as
`# ...`) are elided, and any `# ⚠`-flagged line is an editorial annotation, not emitted
code. Run the commands below to see the full, verbatim output. The map ships in two
identical forms:

- [`spring-to-fastapi.toml`](spring-to-fastapi.toml) — loads via the stdlib, **works out
  of the box** (recommended):

  ```bash
  uv run j2py translate tests/fixtures/corpus/spring-app/OrderController.java \
    -c docs/examples/spring-to-fastapi.toml --no-llm --no-validate --dry-run
  ```

- [`spring-to-fastapi.yaml`](spring-to-fastapi.yaml) — same content; YAML configs require
  the optional PyYAML extra (`uv pip install 'j2py-converter[yaml]'`):

  ```bash
  uv run j2py translate tests/fixtures/corpus/spring-app/OrderController.java \
    -c docs/examples/spring-to-fastapi.yaml --no-llm --no-validate --dry-run
  ```

Both produce byte-identical Python. See [configuration.md](../configuration.md) for the
config-format details.

## What Tier 2 `annotation_map` can and cannot do

`annotation_map` entries are **strict** (`extra="forbid"`). Only these keys exist:

| Key | Effect |
|---|---|
| `python_decorator` | Emit `@<value>` above a mapped class or method. `{value}`, `{name}`, etc. are substituted from annotation arguments. |
| `python_base` | Append a base class to a mapped class declaration. |
| `python_annotation` | Wrap mapped method parameters as `typing.Annotated[<type>, <value>]`. |
| `field_comment` | Emit a comment above a field. Placeholders: `{field_name}`, `{field_type}`, `{java_type}`. |
| `emit_init_param` | Promote an instance field into `__init__` as a required, assigned parameter. |
| `import` | Add one or more import lines required by the mapped output. |
| `drop` | Drop the annotation entirely. |
| `preserve_comment` | Keep/suppress the `# @Annotation(...)` audit comment (defaults to `emit_line_comments`). |

There is **no** key to emit an arbitrary class attribute (e.g. `__tablename__ = ...`), a
column flag (`primary_key=True`), or a router-init line. Those require a Tier 4 plugin
([#337](https://github.com/tomanizer/j2py/issues/337)) or a manual port. Sketches in the
original design notes that used keys like `template:`, `class_attr:`, `column_flag:`, or
`metadata:` are **not valid** and would be rejected by the config loader.

---

## 1. Controllers (`@RestController` / HTTP verb mappings)

Fixture: [`OrderController.java`](../../tests/fixtures/corpus/spring-app/OrderController.java)

### Java

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Order get(@PathVariable Long id) {
        return service.findById(id);
    }

    @PostMapping
    public Order create(@RequestBody Order order) {
        return service.save(order);
    }

    @DeleteMapping("/{id}")
    public void delete(@PathVariable Long id) {
        service.deleteById(id);
    }
}
```

### Python (actual j2py output)

```python
from myapp.spring_shim import rest_controller
from myapp.web import router


# @RestController
# @RequestMapping("/orders")
@rest_controller
@router.api_route("/orders")
class OrderController:
    def __init__(self, service: OrderService) -> None:
        self.service = service

    # @GetMapping("/{id}")
    @router.get("/{id}")
    def get(self, id_: int) -> Order:
        return self.service.find_by_id(id_)

    # @PostMapping
    @router.post("{value}")          # ⚠ see note
    def create(self, order: Order) -> Order:
        return self.service.save(order)

    # @DeleteMapping("/{id}")
    @router.delete("/{id}")
    def delete(self, id_: int) -> None:
        self.service.delete_by_id(id_)
```

### Mapping notes

| Java | Lowering | Status |
|---|---|---|
| `@RestController` | `@rest_controller` shim decorator | ✅ Tier 2 |
| `@RequestMapping("/orders")` | `@router.api_route("/orders")` | ✅ Tier 2 |
| `@GetMapping("/{id}")` | `@router.get("/{id}")` | ✅ Tier 2 |
| `@PathVariable Long id` | param `id_: int` (`Long`→`int`, camel→snake) | ✅ Tier 1 |
| `@PostMapping` (no value) | `@router.post("{value}")` literal | ⚠ wart |

**Manual port required:**

- **`@PostMapping` with no path** → the unresolved `{value}` placeholder is emitted
  *literally*: `@router.post("{value}")`. Fix the handler to `@router.post("")` (or `"/"`)
  by hand, or give the annotation an explicit path in Java. j2py does not invent a default.
- **`self` on handlers.** j2py emits `self` for every instance method; FastAPI handlers
  are plain functions. Route registration / `self` removal is
  [#338 `j2py-wire`](https://github.com/tomanizer/j2py/issues/338) territory, not Tier 2.
- **No `APIRouter()` init line.** `annotation_map` cannot emit `router = APIRouter(...)`.
  Provide it from `myapp.web` (the `import` target) or generate it with `j2py-wire`.

---

## 2. Constructor injection (preferred in modern Spring)

Fixture: [`OrderService.java`](../../tests/fixtures/corpus/spring-app/OrderService.java)

### Java

```java
@Service
public class OrderService {
    private final OrderRepository repo;

    public OrderService(OrderRepository repo) {
        this.repo = repo;
    }
    // ...
}
```

### Python (actual j2py output)

```python
from myapp.spring_shim import service


# @Service
@service
class OrderService:
    def __init__(self, repo: OrderRepository) -> None:
        self.repo = repo

    def find_by_id(self, id_: int) -> Order:
        return self.repo.find_by_id(id_)
    # ...
```

### Mapping notes

- **Translates cleanly today.** An explicit constructor with resolved types becomes
  `__init__` with typed parameters — no `annotation_map` needed for the mechanics.
- `@Service` lowers to a marker `@service` decorator purely so
  [`j2py-wire`](https://github.com/tomanizer/j2py/issues/338) can discover providers. There
  is **no** container registration in core.
- **Manual port:** j2py does **not** emit FastAPI `Depends()` glue. The target
  `get_order_service(repo = Depends(get_order_repo))` provider is
  [#338](https://github.com/tomanizer/j2py/issues/338).

---

## 3. Field injection (legacy Spring `@Autowired`)

Fixture: [`LegacyFieldInjection.java`](../../tests/fixtures/corpus/spring-app/LegacyFieldInjection.java)

### Java

```java
public class LegacyFieldInjection {
    @Autowired
    private OrderRepository repo;

    @Autowired
    private AuditRepository audit;
    // ...
}
```

### Without `annotation_map` (Tier 1 default — the problem)

A field with no constructor lowers to an optional attribute, which is wrong for a required
dependency:

```python
self.repo: OrderRepository | None = None
```

### With `annotation_map` (`emit_init_param: true`) — actual j2py output

```python
class LegacyFieldInjection:
    def __init__(self, repo: OrderRepository, audit: AuditRepository) -> None:
        # @Autowired
        # injected: OrderRepository repo
        self.repo: OrderRepository = repo
        # @Autowired
        # injected: AuditRepository audit
        self.audit: AuditRepository = audit
```

### Mapping notes

| Behavior | Result |
|---|---|
| Each `@Autowired` field → required `__init__` param | ✅ |
| Stable Java declaration order | ✅ (`repo`, then `audit`) |
| `\| None = None` default removed | ✅ |
| `field_comment` audit trail | ✅ (`# injected: ...`) |

- **Mixed constructor + field injection:** if a class has both an explicit constructor and
  `@Autowired` fields, prefer the constructor params; document the conflict policy before
  relying on it (candidate for a future ADR).
- Downstream `Depends()` wiring is the same [#338](https://github.com/tomanizer/j2py/issues/338)
  provider as constructor injection.

---

## 4. JPA entities (`@Entity` / `@Table` / `@Id`)

Fixture: [`OrderEntity.java`](../../tests/fixtures/corpus/spring-app/OrderEntity.java)

### Java

```java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "customer_name")
    private String customerName;

    private double total;
    // getters ...
}
```

### Python (actual j2py output)

```python
from myapp.db import Base
from myapp.db import table


# @Entity
# @Table(name = "orders")
@table("orders")
class OrderEntity(Base):
    def __init__(self) -> None:
        # @Id
        # @GeneratedValue
        self.id_: int | None = None
        # @Column(name = "customer_name")
        self.customer_name: str | None = None
        self.total: float = 0.0
    # getters ...
```

### Mapping notes

| Java | Lowering | Status |
|---|---|---|
| `@Entity` | base class `Base` (`python_base`) | ✅ Tier 2 |
| `@Table(name = "orders")` | `@table("orders")` shim decorator | ⚠ partial |
| `@Id`, `@GeneratedValue`, `@Column` | **audit comments only** | ❌ Tier 4 |

**Manual port required — this is the biggest gap in the cookbook.**

- **Columns are not mapped.** `@Id`, `@GeneratedValue`, and `@Column` survive only as
  audit comments. Fields stay plain attributes (`self.id_: int | None = None`), **not**
  `id_: Mapped[int] = mapped_column(primary_key=True)`. SQLAlchemy declarative column
  mapping needs a Tier 4 plugin ([#337](https://github.com/tomanizer/j2py/issues/337)).
- **`__tablename__`.** Tier 2 cannot emit a class attribute, so the table name rides a
  `@table("orders")` shim decorator (your shim sets `__tablename__` at class-creation time)
  rather than the idiomatic `__tablename__ = "orders"`. Treat the idiomatic form as a
  manual edit or a plugin output.
- **Relationships** (`@OneToMany`, `@ManyToOne`, `@JoinColumn`) are **out of scope** for
  cookbook v1 — follow-up.

For real ORM models, drive entity translation through a Tier 4 plugin or hand-finish the
column declarations after translation.

---

## 5. `@Transactional`

Fixture: [`TransactionalService.java`](../../tests/fixtures/corpus/spring-app/TransactionalService.java)

### Java

```java
@Service
public class TransactionalService {
    private final OrderRepository repo;

    public TransactionalService(OrderRepository repo) {
        this.repo = repo;
    }

    @Transactional
    public Order createOrder(Order order) {
        return repo.save(order);
    }
}
```

### Python (actual j2py output)

```python
from myapp.db import transactional
from myapp.spring_shim import service


# @Service
@service
class TransactionalService:
    def __init__(self, repo: OrderRepository) -> None:
        self.repo = repo

    # @Transactional
    @transactional
    def create_order(self, order: Order) -> Order:
        return self.repo.save(order)
```

Provide a project-owned decorator:

```python
from functools import wraps

def transactional(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        with session.begin():
            return fn(self, *args, **kwargs)
    return wrapper
```

### Mapping notes

- **Clean passthrough.** `@Transactional` → `@transactional`. j2py does **not** transpile
  Spring AOP proxy semantics.

**Manual port required (explicit non-goals):**

- `Propagation.REQUIRES_NEW`, `readOnly = true`, isolation levels.
- Declarative rollback rules (`rollbackFor`, `noRollbackFor`).
- Class-level `@Transactional` applied to all public methods — j2py only lowers
  annotations where they appear; fan-out to methods is a plugin/manual step.

---

## Reference annotation map

The full map ships as [`spring-to-fastapi.toml`](spring-to-fastapi.toml) and
[`spring-to-fastapi.yaml`](spring-to-fastapi.yaml) (identical content) and covers
`RestController`, `RequestMapping`, the HTTP verb mappings, `Service` / `Component` /
`Repository`, `Autowired`, `Entity`, `Table`, and `Transactional`. Copy either into your
project and adapt the `import` targets to your own shim modules.

## Manual-port checklist

When migrating a Spring app with this cookbook, plan to hand-finish:

- [ ] `APIRouter()` initialization and route registration ([#338](https://github.com/tomanizer/j2py/issues/338))
- [ ] Removing `self` from FastAPI handlers; `Depends()` wiring ([#338](https://github.com/tomanizer/j2py/issues/338))
- [ ] `@PostMapping`/`@PutMapping` with no path → fix the literal `{value}` placeholder
- [ ] SQLAlchemy `Mapped`/`mapped_column` column declarations ([#337](https://github.com/tomanizer/j2py/issues/337))
- [ ] `__tablename__` if you want the idiomatic form instead of the shim decorator
- [ ] JPA relationships (`@OneToMany`, `@ManyToOne`, …) — cookbook v2
- [ ] Transaction propagation / rollback rules / isolation
- [ ] Spring Security, `@Scheduled`, `@Cacheable`, `@Async` — cookbook v2

## Non-goals

- Exhaustive Spring annotation coverage.
- A runnable Petclinic from the cookbook alone.
- Spring Security, `@Scheduled`, `@Cacheable`, `@Async` (cookbook v2).
- JPA relationships in v1.
