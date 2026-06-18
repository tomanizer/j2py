from __future__ import annotations

from j2py_runtime import get_mapping, rest_controller


# @RestController
@rest_controller
class SpringAnnotationPreset:

    # @GetMapping("/hello")
    @get_mapping("/hello")
    def hello(self) -> str:
        return "ok"
