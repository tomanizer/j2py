from __future__ import annotations


class PatternMatchSwitch:

    def describe(self, obj: object) -> str:

        def _j2py_switch_1(_j2py_subject: object) -> str:
            match _j2py_subject:
                case int() as i:
                    return f"int: {i}"
                case str() as s if not s:
                    return "empty string"
                case str() as s:
                    return f"string: {s}"
                case None:
                    return "null"
                case _:
                    return f"other: {obj}"
        result = _j2py_switch_1(obj)
        return result
