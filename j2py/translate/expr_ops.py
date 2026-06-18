"""Compatibility facade for operator expression helpers.

Implementation lives in focused ``expr_*`` modules; keep these re-exports while
call sites migrate away from importing the old monolith directly.
"""

from __future__ import annotations

from j2py.translate.expr_assignments import (
    _desugar_embedded_assign as _desugar_embedded_assign,
)
from j2py.translate.expr_assignments import (
    _translate_assignment_expression as _translate_assignment_expression,
)
from j2py.translate.expr_assignments import (
    _translate_update_expression as _translate_update_expression,
)
from j2py.translate.expr_binary import (
    _translate_binary_expression as _translate_binary_expression,
)
from j2py.translate.expr_conditionals import (
    _translate_ternary_expression as _translate_ternary_expression,
)
from j2py.translate.expr_switch import _switch_condition as _switch_condition
from j2py.translate.expr_switch import _switch_label_values as _switch_label_values
from j2py.translate.expr_switch import (
    _translate_switch_expression as _translate_switch_expression,
)
from j2py.translate.expr_unary import (
    _translate_unary_expression as _translate_unary_expression,
)

__all__ = [
    "_desugar_embedded_assign",
    "_switch_condition",
    "_switch_label_values",
    "_translate_assignment_expression",
    "_translate_binary_expression",
    "_translate_switch_expression",
    "_translate_ternary_expression",
    "_translate_unary_expression",
    "_translate_update_expression",
]
