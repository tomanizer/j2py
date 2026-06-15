# ADR 0016 — Class-reference expressions request imports

**Date:** 2026-06-15
**Status:** Accepted

## Context

Java uses the same identifier token shape for local variables, fields, methods,
static members, and type names. In expression position this matters because a
qualified static call such as:

```java
import org.apache.commons.lang3.ArrayUtils;

ArrayUtils.setAll(array, value);
```

is not a call on a local variable named `arrayUtils`; it is a class reference
followed by a static method invocation.

The rule layer already snake-cases normal Java identifiers to keep Python output
reviewable, so treating every identifier as a value name produced invalid output:

```python
array_utils.set_all(array, value)
```

That output loses the Java class reference, emits no import, and usually fails at
runtime with `NameError`. The problem also appears for same-package references,
where Java allows `Peer.fill(values)` without an explicit import.

At the same time, the rule layer does not have a full Java name resolver. The
solution must stay deterministic and reviewable without pretending to infer every
possible classpath binding.

## Decision

Expression translation treats an unshadowed Java type-name token as a class
reference before applying normal field-name snake-casing.

The binding sources are, in order:

1. Explicit non-static Java imports in the current file.
2. Configured `import_map` entries for those Java imports.
3. Same-package uppercase identifiers as a conservative fallback.

Local variables and parameters shadow type-name bindings. Declared class fields
are checked before imported types so static constants such as `VALUES` remain
fields, not same-package class imports. The containing class and nested classes
are also preserved without requesting a module import for themselves.

The skeleton layer owns the file-level import scan and records the result on
`TranslationDiagnostics`:

- `imported_type_names`: Java simple type name -> Python binding in expression
  position.
- `imported_type_imports`: Java simple type name -> Python import line to request
  when that type is used in an expression.
- `package_name`: current Java package for same-package fallback imports.

The expression layer consumes those bindings while translating identifiers. It
requests the import line only when the type is actually referenced in expression
output, which avoids importing unused Java types. Configured import-map lines are
still emitted by the normal import emission path; expression translation only
uses the Python binding name extracted from the mapped import.

Method invocation receivers are translated after static-import and known-static
special cases. That avoids asking the type-reference path to import a receiver
that a more specific rule will translate differently.

## Examples

An explicit Java import keeps the class name and requests a generated import:

```java
import com.example.ExternalThing;

return ExternalThing.create();
```

```python
from com.example.ExternalThing import ExternalThing

return ExternalThing.create()
```

A configured import map keeps the configured Python binding:

```toml
import_map = { "com.example.ExternalThing" = "from ext import Thing" }
```

```java
import com.example.ExternalThing;

return ExternalThing.create();
```

```python
from ext import Thing

return Thing.create()
```

A same-package class reference requests a generated peer import, while a static
field stays a field:

```java
package com.example;

private static final String[] VALUES = new String[1];

static {
    Peer.fill(VALUES);
}
```

```python
from com.example.Peer import Peer

values: list[str] = [None] * 1
Peer.fill(values)
```

## Consequences

+ External and same-package class references in expression position stay close to
  the Java source and produce executable Python for common static calls.
+ Import-map users can redirect Java class references to project-specific Python
  modules without changing expression translation rules.
+ Field and local-name shadowing remains explicit, so uppercase constants are not
  blindly treated as class names.
- Same-package fallback is heuristic. Without a full classpath resolver, an
  uppercase unshadowed identifier in a package can be treated as a peer class
  even if Java would resolve it differently.
- Import binding state now crosses the skeleton/expression boundary through
  diagnostics. That keeps the implementation narrow, but future full symbol
  resolution may deserve a dedicated name-resolution object.

## References

- [Issue #188](https://github.com/tomanizer/j2py/issues/188)
- [ADR 0003](0003-layered-translation-pipeline.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md) material-change ADR rule
