"""Default translation rules and type mappings."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Primitive & boxed type mappings
# ---------------------------------------------------------------------------

TYPE_MAP: dict[str, str] = {
    # primitives
    "boolean": "bool",
    "byte": "int",
    "short": "int",
    "int": "int",
    "long": "int",
    "float": "float",
    "double": "float",
    "char": "str",
    "void": "None",
    # boxed
    "Boolean": "bool",
    "Byte": "int",
    "Short": "int",
    "Integer": "int",
    "Long": "int",
    "Float": "float",
    "Double": "float",
    "Character": "str",
    "String": "str",
    "Object": "object",
    # common java.lang
    "Number": "float",
    "CharSequence": "str",
    "Class": "type",
    "Comparable": "object",
    "Iterable": "Iterable",
    "Cloneable": "object",
    "Serializable": "object",
}

# ---------------------------------------------------------------------------
# Generic collection type mappings  (raw type → Python type)
# ---------------------------------------------------------------------------

COLLECTION_MAP: dict[str, str] = {
    "List": "list",
    "ArrayList": "list",
    "LinkedList": "list",
    "Vector": "list",
    "Set": "set",
    "HashSet": "set",
    "LinkedHashSet": "set",
    "TreeSet": "set",
    "Map": "dict",
    "HashMap": "dict",
    "LinkedHashMap": "dict",
    "TreeMap": "dict",
    "Hashtable": "dict",
    "MultiValueMap": "dict",
    "Properties": "dict",
    "Queue": "collections.deque",
    "Deque": "collections.deque",
    "ArrayDeque": "collections.deque",
    "Stack": "list",
    "Optional": "Optional",  # Optional[T] — needs special handling
    "Iterator": "Iterator",
    "Iterable": "Iterable",
    "Collection": "list",
}

# ---------------------------------------------------------------------------
# Exception type mappings
# ---------------------------------------------------------------------------

EXCEPTION_MAP: dict[str, str] = {
    "Exception": "Exception",
    "RuntimeException": "Exception",
    "IllegalArgumentException": "ValueError",
    "IllegalStateException": "RuntimeError",
    "NullPointerException": "AttributeError",
    "IndexOutOfBoundsException": "IndexError",
    "ArrayIndexOutOfBoundsException": "IndexError",
    "StringIndexOutOfBoundsException": "IndexError",
    "ClassCastException": "TypeError",
    "ArithmeticException": "ArithmeticError",
    "UnsupportedOperationException": "NotImplementedError",
    "IOException": "OSError",
    "SQLException": "OSError",
    "FileNotFoundException": "FileNotFoundError",
    "InterruptedException": "InterruptedError",
    "NumberFormatException": "ValueError",
    "StackOverflowError": "RecursionError",
    "OutOfMemoryError": "MemoryError",
    "AssertionError": "AssertionError",
    "CloneNotSupportedException": "NotImplementedError",
    "NoSuchElementException": "StopIteration",
}

# ---------------------------------------------------------------------------
# Literal token replacements
# ---------------------------------------------------------------------------

LITERAL_MAP: dict[str, str] = {
    "null": "None",
    "true": "True",
    "false": "False",
}

# ---------------------------------------------------------------------------
# Access modifiers to strip (no Python equivalent)
# ---------------------------------------------------------------------------

STRIP_MODIFIERS: frozenset[str] = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "final",
        "abstract",
        "native",
        "volatile",
        "transient",
        "strictfp",
    }
)

# ---------------------------------------------------------------------------
# Annotations to drop silently
# ---------------------------------------------------------------------------

DROP_ANNOTATIONS: frozenset[str] = frozenset(
    {"Override", "SuppressWarnings", "SafeVarargs", "FunctionalInterface", "Deprecated"}
)

# ---------------------------------------------------------------------------
# Java standard imports that map to Python builtins (can be dropped)
# ---------------------------------------------------------------------------

DROP_IMPORTS: frozenset[str] = frozenset(
    {
        "java.lang.String",
        "java.lang.Integer",
        "java.lang.Long",
        "java.lang.Double",
        "java.lang.Float",
        "java.lang.Boolean",
        "java.lang.Object",
        "java.lang.Math",
        "java.lang.System",
        "java.lang.StringBuilder",
        "java.lang.StringBuffer",
        "java.util.List",
        "java.util.ArrayList",
        "java.util.LinkedList",
        "java.util.Map",
        "java.util.HashMap",
        "java.util.LinkedHashMap",
        "java.util.Set",
        "java.util.HashSet",
        "java.util.TreeSet",
        "java.util.Arrays",
        "java.util.Collections",
        "java.util.EnumSet",
        "java.util.Locale",
        "java.util.Optional",
    }
)

IMPORT_MAP: dict[str, str] = {
    "java.util.Iterator": "from typing import Iterator",
    "java.util.function.Function": "from typing import Callable",
    "java.util.function.Predicate": "from typing import Callable",
    "java.util.function.Consumer": "from j2py_runtime import Consumer",
    "java.util.function.Supplier": "from typing import Callable",
    "java.util.stream.Collectors": "",  # handled inline
    "java.io.IOException": "",  # maps to OSError (builtin)
    "java.io.InputStream": "from typing import IO",
    "java.io.OutputStream": "from typing import IO",
    "java.io.BufferedReader": "import io",
    "java.io.PrintWriter": "import io",
    "java.nio.file.Path": "from pathlib import Path",
    "java.nio.file.Paths": "from pathlib import Path",
    "java.nio.file.Files": "import pathlib",
    "java.math.BigDecimal": "from decimal import Decimal",
    "java.math.BigInteger": "",  # int handles arbitrary precision
}

# ---------------------------------------------------------------------------
# Opt-in annotation map presets
# ---------------------------------------------------------------------------

SPRING_ANNOTATION_MAP: dict[str, dict[str, object]] = {
    "RestController": {
        "python_decorator": "rest_controller",
        "import": "from j2py_runtime import rest_controller",
    },
    "Controller": {
        "python_decorator": "controller",
        "import": "from j2py_runtime import controller",
    },
    "RequestMapping": {
        "python_decorator": 'request_mapping("{value}", method="{method}")',
        "import": "from j2py_runtime import request_mapping",
    },
    "GetMapping": {
        "python_decorator": 'get_mapping("{value}")',
        "import": "from j2py_runtime import get_mapping",
    },
    "PostMapping": {
        "python_decorator": 'post_mapping("{value}")',
        "import": "from j2py_runtime import post_mapping",
    },
    "PutMapping": {
        "python_decorator": 'put_mapping("{value}")',
        "import": "from j2py_runtime import put_mapping",
    },
    "DeleteMapping": {
        "python_decorator": 'delete_mapping("{value}")',
        "import": "from j2py_runtime import delete_mapping",
    },
    "PathVariable": {
        "python_annotation": "path_variable",
        "import": "from j2py_runtime import path_variable",
        "preserve_comment": False,
    },
    "RequestBody": {
        "python_annotation": "request_body",
        "import": "from j2py_runtime import request_body",
        "preserve_comment": False,
    },
    "RequestParam": {
        "python_annotation": "request_param",
        "import": "from j2py_runtime import request_param",
        "preserve_comment": False,
    },
    "ResponseStatus": {
        "python_decorator": "response_status({value})",
        "import": "from j2py_runtime import response_status",
    },
    "Component": {
        "python_decorator": "component",
        "import": "from j2py_runtime import component",
    },
    "Service": {
        "python_decorator": "service",
        "import": "from j2py_runtime import service",
    },
    "Repository": {
        "python_decorator": "repository",
        "import": "from j2py_runtime import repository",
    },
    "Configuration": {
        "python_decorator": "configuration",
        "import": "from j2py_runtime import configuration",
    },
    "Bean": {
        "python_decorator": "bean",
        "import": "from j2py_runtime import bean",
    },
    "Autowired": {
        "field_comment": "# @Autowired",
        "emit_init_param": True,
    },
    "Transactional": {
        "python_decorator": "transactional",
        "import": "from j2py_runtime import transactional",
    },
    "Value": {
        "field_comment": '# @Value("{value}")',
    },
    "ConfigurationProperties": {
        "python_decorator": 'configuration_properties(prefix="{prefix}")',
        "import": "from j2py_runtime import configuration_properties",
    },
}
