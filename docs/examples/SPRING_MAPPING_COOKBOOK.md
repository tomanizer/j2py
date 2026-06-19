# Spring → FastAPI/SQLAlchemy mapping cookbook

Reference mappings for lowering the most common Spring application-layer patterns to a
**FastAPI + SQLAlchemy** Python stack. This is a **guide and fixture spec**, not full
Spring support in j2py core.

j2py enables **no** Spring, FastAPI, JPA, or DI semantics by default
([ADR 0019](../decisions/0019-annotation-map-framework-lowering.md)). The core package
does include `annotation_map_preset: spring` for no-op Spring marker decorators; the
FastAPI/SQLAlchemy profile in this cookbook remains project policy realized through the
tiers below. Product scope and architectural boundaries for the optional Spring extension
are recorded in [SPRING_EXTENSION_PRD.md](../SPRING_EXTENSION_PRD.md) and
[ADR 0024](../decisions/0024-spring-extension-boundary.md).

| Tier | Mechanism | Status | Issue |
|---|---|---|---|
| Tier 1 | Default lowering + audit comments | shipped | — |
| Tier 2 | `annotation_map` config | shipped | [#335](https://github.com/tomanizer/j2py/issues/335) |
| Tier 4 | Framework plugins (richer transforms and sidecar metadata) | shipped | [ADR 0022](../decisions/0022-framework-plugin-architecture.md) |
| Tier 5 | `j2py-wire` (DI/route bootstrap from sidecars) | shipped | [Spring conversion guide](../SPRING_CONVERSION.md) |

Related: [#333](https://github.com/tomanizer/j2py/issues/333) (enterprise audit),
[#334](https://github.com/tomanizer/j2py/issues/334) (annotation visibility),
[#339](https://github.com/tomanizer/j2py/issues/339) (this cookbook). Historical
implementation issues for framework plugins, `j2py-wire`, and Spring JDBC are now
represented by the shipped guides linked from this page.

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
column flag (`primary_key=True`), or a router-init line. Those require a Tier 4 plugin,
`j2py-wire`, or a manual port depending on whether the fact belongs in translated source
or generated wiring. Sketches in the
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
  are plain functions. Route registration and handler adaptation belong in generated
  wiring from `j2py-wire`, not Tier 2 annotation output.
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
  `j2py-wire` can discover providers from sidecars. There is **no** container registration
  in core.
- **Manual port:** j2py does **not** emit FastAPI `Depends()` glue. The target
  application or generated `j2py-wire` output must bind a provider such as
  `get_order_service(repo = Depends(get_order_repo))`.

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
- Downstream `Depends()` wiring is the same `j2py-wire`/application boundary as
  constructor injection.

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
  mapping needs a Tier 4 plugin or project-owned ORM generation policy.
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

## 6. Spring JDBC (`DataSource` / `JdbcTemplate`)

Spring JDBC support should be **SQLAlchemy-first**, not native-JDBC-first. In typical
Spring applications, JDBC access is configured through beans:

```java
@Configuration
public class JdbcConfig {
    @Autowired
    private Environment env;

    @Bean
    DataSource dataSource() {
        return DataSourceBuilder.create()
            .url(env.getProperty("app.datasource.url"))
            .username(env.getProperty("app.datasource.username"))
            .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

j2py should discover that bean topology before attempting any data-access lowering. The
useful facts are not "there is a Java `DataSource` class"; they are:

- which `@Bean` methods provide `DataSource`, `JdbcTemplate`,
  `NamedParameterJdbcTemplate`, or a transaction manager;
- which repositories/services receive those beans through constructors or `@Autowired`;
- which property names or project shims are visible for URL, username, driver, or session
  factory setup;
- which calls are plain enough to lower to reviewable SQLAlchemy Core scaffolding.

### Recommended target split

| Option | Recommendation | Reason |
|---|---|---|
| SQLAlchemy Core/ORM | Recommended target | Matches existing j2py Spring/JPA work, gives reviewable Python DB code, and leaves dialect choice to the project. |
| pyodbc | Driver/dialect only | Use behind SQLAlchemy (`mssql+pyodbc`) or a project-owned DB shim; do not emit pyodbc-specific code from core. |
| JayDeBeApi / native JDBC bridge | Avoid as migration target | Keeps the Java runtime boundary alive and works against ADR 0020's no-JDBC-runtime policy. |
| Raw `java.sql` translation | Boundary stubs only | Preserve signatures and TODOs; do not emit fake `from java.sql ...` imports. |

### Plugin/config boundary

Keep the Spring JDBC route opt-in:

- Core translation preserves raw `java.sql.*` / `javax.sql.*` boundaries as local
  placeholders, `Any`, or explicit `# TODO(j2py): JDBC boundary` comments.
- A Spring framework plugin records `@Configuration` / `@Bean` JDBC metadata in
  `*.wiring.json` sidecars.
- Deterministic call lowering can handle common `JdbcTemplate.update(...)`,
  `query(...)`, `queryForObject(...)`, simple `RowMapper` forms, and named-parameter
  forms only when the generated SQLAlchemy Core scaffold remains visibly equivalent to the
  Java source.
- Project config owns real imports, engine/session construction, dialect URLs, and
  database-specific behavior. For SQL Server, that may still mean `pyodbc`, but through
  SQLAlchemy or an internal `myapp.db` facade.
- ADR 0020 remains the boundary: j2py lowers reviewable call structure and metadata, not a
  native JDBC runtime or driver bridge.

### Current deterministic JDBC lowering

The rule layer now recognizes the common Spring JDBC repository surface and emits
SQLAlchemy Core scaffolding. It does not create a live engine or session; the generated
receiver names are placeholders that make the expected dependency explicit:

| Java source shape | Python scaffold |
|---|---|
| `jdbcTemplate.update(sql, id)` | `self.jdbc_template_connection.execute(text(sql), {"p1": id_}).rowcount` |
| `jdbcTemplate.queryForObject(sql, Integer.class, id)` | `self.jdbc_template_connection.execute(text(sql), {"p1": id_}).scalar_one()` |
| `namedJdbcTemplate.update(sql, params)` | `self.named_jdbc_template_connection.execute(text(sql), params).rowcount` |
| `jdbcTemplate.query(sql, rowMapper)` | `[... for row in self.jdbc_template_connection.execute(text(sql)).mappings()]` |
| `namedJdbcTemplate.queryForObject(sql, params, rowMapper)` | `(lambda row: ...)(self.named_jdbc_template_connection.execute(text(sql), params).mappings().one())` |

These examples are backed by the fixture
[`JdbcTemplateSqlAlchemyScaffold.java`](../../tests/fixtures/java/JdbcTemplateSqlAlchemyScaffold.java):

```java
return jdbcTemplate.update(
        "update owners set first_name = ? where id = ?",
        firstName,
        id);
```

```python
return self.jdbc_template_connection.execute(
    text('update owners set first_name = :p1 where id = :p2'),
    {'p1': first_name, 'p2': id_},
).rowcount
```

```java
return namedJdbcTemplate.queryForObject(
        "select name from owners where id = :id",
        params,
        String.class);
```

```python
return self.named_jdbc_template_connection.execute(
    text('select name from owners where id = :id'),
    params,
).scalar_one()
```

Supported row-mapping forms are intentionally simple:

- Lambda mappers whose body is a single expression, for example
  `(rs, rowNum) -> new Owner(rs.getLong("id"), rs.getString("name"))`.
- Anonymous `new RowMapper<T>() { mapRow(...) { return ...; } }` classes when `mapRow`
  has a single return expression.
- `BeanPropertyRowMapper.newInstance(Owner.class)` and
  `new BeanPropertyRowMapper<>(Owner.class)`, rendered as `Owner(**dict(row))`.
- Common `ResultSet` getters with string-literal column names:
  `getString`, `getInt`, `getLong`, `getBoolean`, `getBigDecimal`, `getDate`, and
  `getTimestamp`, rendered as `row["column"]`.

The fixture [`JdbcRowMapperScaffold.java`](../../tests/fixtures/java/JdbcRowMapperScaffold.java)
shows the current RowMapper boundary:

```java
return jdbcTemplate.query(
        "select id, first_name, last_name from owners",
        (rs, rowNum) -> new Owner(
                rs.getLong("id"),
                rs.getString("first_name"),
                rs.getString("last_name")));
```

```python
return [
    Owner(row['id'], row['first_name'], row['last_name'])
    for row in self.jdbc_template_connection.execute(
        text('select id, first_name, last_name from owners')
    ).mappings()
]
```

```java
return jdbcTemplate.queryForObject(
        "select id, first_name, last_name from owners where id = ?",
        this::mapOwner,
        id);
```

```python
return __j2py_todo__(
    'TODO(j2py): JdbcTemplate RowMapper/callback requires project row mapping'
)
```

Unsupported mapper and callback shapes stay explicit. Method references, dynamic column
lookups, multi-statement `mapRow` bodies, `ResultSetExtractor`, generated keys, batch
updates, stored procedures, vendor-specific result handling, and transaction/runtime
policy still emit TODO diagnostics or remain manual-port work. That is deliberate: these
cases usually require application-specific model construction, null policy, dialect
behavior, or transaction scoping.

### Recommended j2py flow

Use the Spring wiring plugin when translating bean-configured JDBC packages:

```python
# j2py_config.py
from j2py.framework_plugins.spring import SpringWiringPlugin as _SpringWiringPlugin

annotation_map_preset = "spring"
framework_plugins = [_SpringWiringPlugin()]
emit_wiring_metadata = True
```

Run translation with that trusted project config, then inspect both outputs:

1. The translated repository methods show SQLAlchemy Core scaffolding for simple
   `JdbcTemplate.update(...)`, `query(...)`, `queryForObject(...)`, simple RowMapper, and
   named-parameter variants, for example
   `connection.execute(text("..."), params).scalar_one()` or
   `[Owner(row["id"], row["name"]) for row in connection.execute(text("...")).mappings()]`.
2. The `*.wiring.json` sidecar records `DataSource`, `JdbcTemplate`,
   `NamedParameterJdbcTemplate`, and transaction-manager bean topology, including visible
   `Environment.getProperty(...)` keys.
3. Project code or a downstream generator turns those sidecar facts into the real
   SQLAlchemy `Engine`, `Connection`, or `Session` dependency. That layer chooses the URL,
   pool settings, transaction scope, and dialect such as `postgresql`, `sqlite`, or
   `mssql+pyodbc`.

The generated repository placeholders deliberately stay reviewable instead of runnable:
`self.jdbc_template_connection` or `self.named_jdbc_template_connection` is a signal to
wire an equivalent SQLAlchemy dependency from the bean metadata.

For a focused local verification pass, run:

```bash
uv run --extra test pytest \
  tests/translate/test_jdbc_sqlalchemy_calls.py \
  tests/translate/test_jdbc_row_mapper.py \
  tests/translate/skeleton/test_spring_wiring_plugin.py -q
```

### Manual port required

- Complex `RowMapper` bodies, method-reference mappers, `ResultSetExtractor`, callbacks,
  generated keys, batch updates, stored procedures, and vendor SQL behavior.
- Transaction propagation, isolation, read-only hints, and rollback rules beyond a
  project-owned `@transactional` shim.
- Production engine/session lifecycle. `j2py-wire` can generate application wiring
  scaffolding, but the application remains responsible for its database runtime policy.

See the [Spring conversion guide](../SPRING_CONVERSION.md) for the end-to-end
translate -> sidecar -> wire -> smoke-test flow.

---

## Reference annotation map

The full map ships as [`spring-to-fastapi.toml`](spring-to-fastapi.toml) and
[`spring-to-fastapi.yaml`](spring-to-fastapi.yaml) (identical content) and covers
`RestController`, `RequestMapping`, the HTTP verb mappings, `Service` / `Component` /
`Repository`, `Autowired`, `Entity`, `Table`, and `Transactional`. Copy either into your
project and adapt the `import` targets to your own shim modules.

## Manual-port checklist

When migrating a Spring app with this cookbook, plan to hand-finish:

- [ ] `APIRouter()` initialization and route registration, if not generated with
      `j2py-wire`
- [ ] Removing `self` from FastAPI handlers; `Depends()` wiring, if not generated with
      `j2py-wire`
- [ ] `@PostMapping`/`@PutMapping` with no path → fix the literal `{value}` placeholder
- [ ] SQLAlchemy `Mapped`/`mapped_column` column declarations
- [ ] `__tablename__` if you want the idiomatic form instead of the shim decorator
- [ ] JPA relationships (`@OneToMany`, `@ManyToOne`, …) — cookbook v2
- [ ] Production SQLAlchemy engine/session lifecycle for Spring JDBC bean metadata
- [ ] Complex Spring JDBC callbacks, row mappers, generated keys, and batch updates
- [ ] Transaction propagation / rollback rules / isolation
- [ ] Spring Security, `@Scheduled`, `@Cacheable`, `@Async` — cookbook v2

## Non-goals

- Exhaustive Spring annotation coverage.
- A runnable Petclinic from the cookbook alone.
- Spring Security, `@Scheduled`, `@Cacheable`, `@Async` (cookbook v2).
- JPA relationships in v1.
- Native JDBC/JayDeBeApi runtime emulation or pyodbc-first code generation.
