"""Stable contract surface shared between j2py core and the j2py-wire consumer.

The core translator *produces* ``*.wiring.json`` sidecars; the ``j2py.wire`` package
(and any out-of-core sidecar consumer such as a future ``j2py-spring-fastapi``) *reads*
them. The only things both sides must agree on are:

* :data:`WIRING_METADATA_SCHEMA_VERSION` — the sidecar envelope version, so consumers can
  reject incompatible payloads; and
* :func:`translate_field_name` — the Java→Python field-name transform, so generated wiring
  references the same identifiers the translator emitted.

This module is the *single* place a sidecar consumer is permitted to import from core
(enforced by ``tests/test_import_boundary.py``). ``WIRING_METADATA_SCHEMA_VERSION`` is
defined here; ``translate_field_name`` is re-exported from its canonical home in
``j2py.translate.rules.naming``. In both cases the consumer never needs to reach into
``j2py.pipeline`` or ``j2py.translate.*`` (both Internal per
``docs/developer/API_STABILITY.md``). See ADR 0022 (framework plugin architecture) and
ADR 0024 (Spring extension boundary).
"""

from __future__ import annotations

from j2py.translate.rules.naming import translate_field_name

# Canonical home for the sidecar envelope version. ``j2py.pipeline`` re-exports this for
# backwards compatibility, but new code (core or consumer) should import it from here.
WIRING_METADATA_SCHEMA_VERSION = 1

__all__ = [
    "WIRING_METADATA_SCHEMA_VERSION",
    "translate_field_name",
]
