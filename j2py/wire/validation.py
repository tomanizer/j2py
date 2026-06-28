"""Validation checks for generated j2py-wire output."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from j2py.wire.schema import WiringElement, WiringSidecar
from j2py.wire.targets.providers import (
    PROVIDERS_FILENAME,
    expected_provider_names,
    missing_injection_provider_edges,
    provider_cycles,
    provider_name_collisions,
)
from j2py.wire.targets.sqlalchemy import (
    DB_FILENAME,
    PERSISTENCE_FILENAME,
    has_sqlalchemy_persistence_facts,
    missing_placeholder_bindings,
    transaction_facts,
)

Severity = Literal["error", "warning"]
_DEFAULT_ALLOWED_IMPORT_MODULES = {
    "__future__",
    "fastapi",
    "sqlalchemy.orm",
}
_SQLALCHEMY_ALLOWED_IMPORT_MODULES = _DEFAULT_ALLOWED_IMPORT_MODULES | {
    "collections.abc",
    "contextlib",
    "sqlalchemy",
    "sqlalchemy.engine",
}


class ValidationCheck(Protocol):
    def run(self, context: ValidationContext) -> list[ValidationFinding]: ...


@dataclass(frozen=True)
class ValidationFinding:
    severity: Severity
    code: str
    path: str
    message: str
    fix: str
    line: int | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "fix": self.fix,
        }


@dataclass(frozen=True)
class ValidationContext:
    translated_root: Path
    wiring_dir: Path
    sidecars: list[WiringSidecar]


class SpringProfileCheck:
    code = "spring-profile"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for sidecar in context.sidecars:
            for element in sidecar.elements:
                spring = element.spring
                if not spring:
                    continue
                if spring.get("profile_version") != 1:
                    findings.append(
                        _finding(
                            self.code,
                            sidecar.output,
                            f"{element.kind} {element.java_name} has unsupported Spring profile",
                            "Regenerate sidecars with Spring wiring profile_version 1",
                            severity="error",
                        ),
                    )
                findings.extend(_validate_spring_element(self.code, sidecar, element))
        return findings


class SpringBeanDefinitionCheck:
    code = "spring-bean"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        bean_defs = _bean_definitions(context.sidecars)
        provider_names = {
            _normalize_bean_identity(provider)
            for sidecar in context.sidecars
            for element in sidecar.elements
            for provider in _spring_provider_names(element)
        }
        findings: list[ValidationFinding] = []

        # Index beans by every name they can be resolved by (canonical + aliases)
        # so that a duplicate alias produces a finding alongside a duplicate name.
        # Deduplicate per-bean identity names first — if a bean lists its own
        # canonical name as an alias, a single set prevents self-false-positives.
        beans_by_name: dict[str, list[tuple[WiringSidecar, WiringElement, dict[str, object]]]] = {}
        for sidecar, element, bean in bean_defs:
            names_to_register: set[str] = set()
            name = bean.get("name")
            if isinstance(name, str) and name:
                names_to_register.add(name)
            aliases = bean.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and alias:
                        names_to_register.add(alias)
            for n in names_to_register:
                beans_by_name.setdefault(n, []).append((sidecar, element, bean))

        for name, records in beans_by_name.items():
            if len(records) < 2:
                continue
            for sidecar, element, bean in records:
                findings.append(
                    _finding(
                        self.code,
                        sidecar.source,
                        f"Duplicate Spring bean name '{name}' on {element.java_name}",
                        "Rename one bean or add explicit project wiring policy",
                        severity="error",
                        line=_source_line(bean),
                    ),
                )

        for sidecar, element, bean in bean_defs:
            dependencies = bean.get("dependencies")
            if not isinstance(dependencies, list):
                continue
            for dependency in dependencies:
                if not isinstance(dependency, dict):
                    continue
                dep_name = dependency.get("name")
                if not isinstance(dep_name, str) or not dep_name:
                    continue
                if _normalize_bean_identity(dep_name) in provider_names:
                    continue
                findings.append(
                    _finding(
                        self.code,
                        sidecar.source,
                        (
                            f"Spring bean '{bean.get('name', element.java_name)}' depends on "
                            f"unresolved provider '{dep_name}'"
                        ),
                        (
                            "Translate or define the provider sidecar, or wire this "
                            "dependency manually"
                        ),
                        severity="warning",
                        line=_source_line(bean),
                    ),
                )
        return findings


class MissingProviderCheck:
    code = "missing-provider"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for controller in _controllers(context):
            source = _read_text(controller.wiring_file)
            for injection in controller.injections:
                provider = f"def get_{injection}"
                if provider not in source:
                    findings.append(
                        _finding(
                            self.code,
                            str(controller.wiring_file),
                            f"Missing provider for injected dependency '{injection}'",
                            "Re-run j2py-wire generate or add the provider function",
                            severity="error",
                        ),
                    )
        return findings


class UnresolvedImportCheck:
    code = "unresolved-import"

    def __init__(self, allowed_import_modules: set[str] | None = None) -> None:
        self.allowed_import_modules = (
            allowed_import_modules
            if allowed_import_modules is not None
            else _DEFAULT_ALLOWED_IMPORT_MODULES
        )

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for path in _wiring_files(context.wiring_dir):
            tree = _parse_python(path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.module is None:
                    continue
                module = node.module
                if module in self.allowed_import_modules:
                    continue
                if module.startswith(f"{context.wiring_dir.name}."):
                    if not _module_exists(context.wiring_dir.parent, module):
                        findings.append(
                            _unresolved_import(path, node.lineno, module, "generated wiring"),
                        )
                    continue
                if not _module_exists(context.translated_root, module):
                    findings.append(_unresolved_import(path, node.lineno, module, "translated"))
        return findings


class RouteHandlerCheck:
    code = "route-handler"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for controller in _controllers(context):
            methods = _class_methods(controller.module_file, controller.class_name)
            for route in controller.routes:
                if route.handler not in methods:
                    findings.append(
                        _finding(
                            self.code,
                            str(controller.module_file),
                            f"Route handler '{route.handler}' not found on {controller.class_name}",
                            f"Check translated {controller.class_name} for method name mismatch",
                            severity="warning",
                        ),
                    )
        return findings


class RouteParameterCheck:
    code = "route-parameter"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for controller in _controllers(context):
            signatures = _function_signatures(controller.wiring_file)
            for route in controller.routes:
                signature = signatures.get(route.handler)
                if signature is None:
                    continue
                expected = set(route.parameters)
                missing = sorted(expected - set(signature.parameters))
                for name in missing:
                    findings.append(
                        _finding(
                            self.code,
                            str(controller.wiring_file),
                            f"Generated route '{route.handler}' is missing parameter '{name}'",
                            "Re-run j2py-wire generate from current sidecars",
                            severity="warning",
                            line=signature.line,
                        ),
                    )
                extra_required = sorted(
                    name
                    for name in signature.required_parameters
                    if name not in expected and name != "controller"
                )
                for name in extra_required:
                    findings.append(
                        _finding(
                            self.code,
                            str(controller.wiring_file),
                            (
                                f"Generated route '{route.handler}' has unexpected "
                                f"required parameter '{name}'"
                            ),
                            "Check route metadata and generated handler signature",
                            severity="warning",
                            line=signature.line,
                        ),
                    )
        return findings


class MissingSessionFactoryCheck:
    code = "missing-session-factory"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for path in _wiring_files(context.wiring_dir):
            source = _read_text(path)
            if (
                "def get_session(" in source
                and "TODO(j2py): replace with your session factory" in source
            ):
                findings.append(
                    _finding(
                        self.code,
                        str(path),
                        "No session factory found - get_session is a stub",
                        "Create a SQLAlchemy session factory and update get_session",
                        severity="warning",
                    ),
                )
        return findings


class OrphanControllerCheck:
    code = "orphan-controller"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for controller in _controllers(context):
            if not controller.wiring_file.exists():
                findings.append(
                    _finding(
                        self.code,
                        str(controller.wiring_file),
                        f"Controller {controller.class_name} has no generated wiring file",
                        "Run j2py-wire generate for the translated output tree",
                        severity="error",
                    ),
                )
        return findings


class OrphanProvidersModuleCheck:
    code = "orphan-providers"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        if not expected_provider_names(context.sidecars, context.translated_root):
            return []
        providers_file = context.wiring_dir / PROVIDERS_FILENAME
        if providers_file.exists():
            return []
        return [
            _finding(
                self.code,
                str(providers_file),
                "Generated providers module is missing",
                "Run j2py-wire generate --target providers",
                severity="error",
            ),
        ]


class ProviderFunctionCheck:
    code = "provider-function"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        providers_file = context.wiring_dir / PROVIDERS_FILENAME
        source = _read_text(providers_file)
        if not source:
            return []
        findings: list[ValidationFinding] = []
        provider_names = expected_provider_names(context.sidecars, context.translated_root)
        for provider_name in sorted(provider_names):
            if f"def {provider_name}(" in source:
                continue
            findings.append(
                _finding(
                    self.code,
                    str(providers_file),
                    f"Missing generated provider function '{provider_name}'",
                    "Run j2py-wire generate --target providers from current sidecars",
                    severity="error",
                ),
            )
        return findings


class ProviderNameCollisionCheck:
    code = "provider-name-collision"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for provider_name, specs in sorted(
            provider_name_collisions(context.sidecars, context.translated_root).items(),
        ):
            identities = ", ".join(sorted(spec.identity for spec in specs))
            findings.append(
                _finding(
                    self.code,
                    str(context.wiring_dir / PROVIDERS_FILENAME),
                    f"Provider function '{provider_name}' maps multiple identities: {identities}",
                    "Rename one component or add explicit project wiring policy",
                    severity="error",
                ),
            )
        return findings


class ProviderDependencyCheck:
    code = "provider-dependency"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for sidecar, element, name in missing_injection_provider_edges(
            context.sidecars,
            context.translated_root,
        ):
            findings.append(
                _finding(
                    self.code,
                    sidecar.source,
                    f"Injected dependency '{name}' has no generated provider edge",
                    "Translate or define the dependency sidecar, or pass this dependency manually",
                    severity="warning",
                    line=_spring_source_line(element),
                ),
            )
        return findings


class ProviderCycleCheck:
    code = "provider-cycle"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for cycle in provider_cycles(context.sidecars, context.translated_root):
            findings.append(
                _finding(
                    self.code,
                    str(context.wiring_dir / PROVIDERS_FILENAME),
                    "Provider dependency cycle detected: " + ", ".join(cycle),
                    "Break the cycle manually or add project-owned provider construction",
                    severity="warning",
                ),
            )
        return findings


class OrphanSQLAlchemyPersistenceCheck:
    code = "orphan-sqlalchemy-persistence"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        if not has_sqlalchemy_persistence_facts(context.sidecars, context.translated_root):
            return []
        findings: list[ValidationFinding] = []
        for filename in [DB_FILENAME, PERSISTENCE_FILENAME]:
            path = context.wiring_dir / filename
            if path.exists():
                continue
            findings.append(
                _finding(
                    self.code,
                    str(path),
                    f"Generated SQLAlchemy wiring file '{filename}' is missing",
                    "Run j2py-wire generate --target sqlalchemy",
                    severity="error",
                ),
            )
        return findings


class SQLAlchemyDatabasePolicyCheck:
    code = "sqlalchemy-database-policy"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        if not has_sqlalchemy_persistence_facts(context.sidecars, context.translated_root):
            return []
        db_file = context.wiring_dir / DB_FILENAME
        source = _read_text(db_file)
        if (
            "DATASOURCE_PROPERTIES" not in source
            or "TODO(j2py): replace DATABASE_URL" not in source
        ):
            return []
        return [
            _finding(
                self.code,
                str(db_file),
                "SQLAlchemy database URL is still the generated placeholder policy",
                "Map datasource property keys to project settings and configure Engine creation",
                severity="warning",
            ),
        ]


class SQLAlchemyPlaceholderBindingCheck:
    code = "sqlalchemy-placeholder-binding"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        persistence_file = context.wiring_dir / PERSISTENCE_FILENAME
        source = _read_text(persistence_file)
        if not source:
            return []
        findings: list[ValidationFinding] = []
        for repository, placeholder in missing_placeholder_bindings(
            context.sidecars,
            context.translated_root,
            source,
        ):
            findings.append(
                _finding(
                    self.code,
                    str(persistence_file),
                    (
                        f"Repository {repository.class_name} expects JDBC placeholder "
                        f"'{placeholder}' but generated persistence wiring does not bind it"
                    ),
                    "Re-run j2py-wire generate --target sqlalchemy from current sidecars",
                    severity="error",
                ),
            )
        return findings


class SQLAlchemyTransactionPolicyCheck:
    code = "sqlalchemy-transaction-policy"

    def run(self, context: ValidationContext) -> list[ValidationFinding]:
        facts = transaction_facts(context.sidecars)
        if not facts:
            return []
        db_file = context.wiring_dir / DB_FILENAME
        source = _read_text(db_file)
        if "TODO(j2py): Spring transaction facts were detected" not in source:
            return []
        return [
            _finding(
                self.code,
                str(db_file),
                "Spring transaction facts require project-owned SQLAlchemy transaction policy",
                (
                    "Map @Transactional, transaction-manager beans, rollback rules, "
                    "propagation, isolation, and read-only behavior manually"
                ),
                severity="warning",
            ),
        ]


FASTAPI_CHECKS: list[ValidationCheck] = [
    SpringProfileCheck(),
    SpringBeanDefinitionCheck(),
    OrphanControllerCheck(),
    UnresolvedImportCheck(),
    MissingProviderCheck(),
    RouteHandlerCheck(),
    RouteParameterCheck(),
    MissingSessionFactoryCheck(),
]

PROVIDERS_CHECKS: list[ValidationCheck] = [
    SpringProfileCheck(),
    SpringBeanDefinitionCheck(),
    OrphanProvidersModuleCheck(),
    UnresolvedImportCheck(),
    ProviderFunctionCheck(),
    ProviderNameCollisionCheck(),
    ProviderDependencyCheck(),
    ProviderCycleCheck(),
]

SQLALCHEMY_CHECKS: list[ValidationCheck] = [
    SpringProfileCheck(),
    SpringBeanDefinitionCheck(),
    OrphanSQLAlchemyPersistenceCheck(),
    UnresolvedImportCheck(_SQLALCHEMY_ALLOWED_IMPORT_MODULES),
    SQLAlchemyPlaceholderBindingCheck(),
    SQLAlchemyDatabasePolicyCheck(),
    SQLAlchemyTransactionPolicyCheck(),
]


def validate_fastapi_wiring(context: ValidationContext) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for check in FASTAPI_CHECKS:
        findings.extend(check.run(context))
    return findings


def validate_providers_wiring(context: ValidationContext) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for check in PROVIDERS_CHECKS:
        findings.extend(check.run(context))
    return findings


def validate_sqlalchemy_wiring(context: ValidationContext) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for check in SQLALCHEMY_CHECKS:
        findings.extend(check.run(context))
    return findings


def validation_exit_code(findings: list[ValidationFinding]) -> int:
    if any(finding.severity == "error" for finding in findings):
        return 2
    if any(finding.severity == "warning" for finding in findings):
        return 1
    return 0


@dataclass(frozen=True)
class _Controller:
    class_name: str
    sidecar: WiringSidecar
    wiring_file: Path
    module_file: Path
    injections: list[str]
    routes: list[_Route]


@dataclass(frozen=True)
class _Route:
    handler: str
    parameters: list[str]


@dataclass(frozen=True)
class _Signature:
    line: int
    parameters: list[str]
    required_parameters: list[str]


def _controllers(context: ValidationContext) -> list[_Controller]:
    controllers: list[_Controller] = []
    for sidecar in context.sidecars:
        module_file = Path(sidecar.output)
        stem = module_file.stem
        wiring_file = context.wiring_dir / f"{stem}_wiring.py"
        for element in sidecar.elements:
            if element.kind == "class" and element.spring.get("role") == "controller":
                controllers.append(
                    _Controller(
                        class_name=element.python_name,
                        sidecar=sidecar,
                        wiring_file=wiring_file,
                        module_file=module_file,
                        injections=_injection_names(sidecar.elements),
                        routes=_route_specs(sidecar.elements),
                    ),
                )
    return controllers


def _injection_names(elements: list[WiringElement]) -> list[str]:
    names: list[str] = []
    for element in elements:
        inject = element.spring.get("inject")
        if isinstance(inject, dict) and isinstance(inject.get("name"), str):
            names.append(inject["name"])
    return names


def _route_specs(elements: list[WiringElement]) -> list[_Route]:
    routes: list[_Route] = []
    for element in elements:
        route = element.spring.get("route")
        if not isinstance(route, dict):
            continue
        handler = route.get("handler")
        if not isinstance(handler, str):
            handler = element.python_name
        routes.append(_Route(handler=handler, parameters=_route_parameters(route)))
    return routes


def _route_parameters(route: dict[str, object]) -> list[str]:
    names: list[str] = []
    parameters = route.get("parameters")
    if isinstance(parameters, list):
        for parameter in parameters:
            if isinstance(parameter, dict) and isinstance(parameter.get("name"), str):
                source = parameter.get("source")
                if source in {"path", "query"}:
                    names.append(parameter["name"])
    request_body = route.get("request_body")
    if isinstance(request_body, dict) and isinstance(request_body.get("name"), str):
        names.append(request_body["name"])
    return names


def _bean_definitions(
    sidecars: list[WiringSidecar],
) -> list[tuple[WiringSidecar, WiringElement, dict[str, object]]]:
    beans: list[tuple[WiringSidecar, WiringElement, dict[str, object]]] = []
    for sidecar in sidecars:
        for element in sidecar.elements:
            bean = element.spring.get("bean")
            if isinstance(bean, dict):
                beans.append((sidecar, element, bean))
    return beans


def _normalize_bean_identity(name: str) -> str:
    """Canonical form for bean-name comparison across camelCase and snake_case.

    Provider names come from Spring (camelCase: ``ownerRepository``) while
    dependency names come from translated Python parameters (snake_case:
    ``owner_repository``). Stripping underscores and lowercasing both sides
    makes them comparable without losing real identity collisions.
    """
    return name.lower().replace("_", "")


def _spring_provider_names(element: WiringElement) -> list[str]:
    # v1 resolves providers by name only (bean.name, bean.aliases, component_name).
    # Type-based, @Qualifier, and @Primary resolution are intentionally out of
    # scope — this is a migration-readiness signal, not a Spring container.
    spring = element.spring
    names: list[str] = []
    bean = spring.get("bean")
    if isinstance(bean, dict):
        if isinstance(bean.get("name"), str):
            names.append(bean["name"])
        aliases = bean.get("aliases", [])
        if isinstance(aliases, list):
            names.extend(a for a in aliases if isinstance(a, str))
    component_name = spring.get("component_name")
    if isinstance(component_name, str):
        names.append(component_name)
    return names


def _source_line(bean: dict[str, object]) -> int | None:
    location = bean.get("source_location")
    if not isinstance(location, dict):
        return None
    line = location.get("line")
    if isinstance(line, int):
        return line
    return None


def _spring_source_line(element: WiringElement) -> int | None:
    source_location = element.spring.get("source_location")
    if not isinstance(source_location, dict):
        inject = element.spring.get("inject")
        if isinstance(inject, dict):
            source_location = inject.get("source_location")
    if not isinstance(source_location, dict):
        return None
    line = source_location.get("line")
    return line if isinstance(line, int) else None


def _validate_spring_element(
    code: str,
    sidecar: WiringSidecar,
    element: WiringElement,
) -> list[ValidationFinding]:
    spring = element.spring
    findings: list[ValidationFinding] = []
    if spring.get("role") == "controller" and not isinstance(spring.get("router_prefix"), str):
        findings.append(
            _finding(
                code,
                sidecar.output,
                f"Controller {element.java_name} is missing router_prefix",
                "Regenerate sidecars with class-level RequestMapping metadata",
                severity="error",
            ),
        )
    route = spring.get("route")
    if isinstance(route, dict):
        for key in ["http_method", "path", "handler", "parameters"]:
            if key not in route:
                findings.append(
                    _finding(
                        code,
                        sidecar.output,
                        f"Route {element.java_name} is missing '{key}'",
                        "Regenerate sidecars with complete route metadata",
                        severity="error",
                    ),
                )
    inject = spring.get("inject")
    if isinstance(inject, dict):
        for key in ["name", "type", "source"]:
            if key not in inject:
                findings.append(
                    _finding(
                        code,
                        sidecar.output,
                        f"Injection {element.java_name} is missing '{key}'",
                        "Regenerate sidecars with complete injection metadata",
                        severity="error",
                    ),
                )
    return findings


def _wiring_files(wiring_dir: Path) -> list[Path]:
    if not wiring_dir.exists():
        return []
    return sorted(wiring_dir.glob("*.py"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse_python(path: Path) -> ast.Module | None:
    if not path.exists():
        return None
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _module_exists(root: Path, module: str) -> bool:
    module_path = root.joinpath(*module.split("."))
    return module_path.with_suffix(".py").exists() or (module_path / "__init__.py").exists()


def _unresolved_import(path: Path, line: int, module: str, kind: str) -> ValidationFinding:
    return _finding(
        UnresolvedImportCheck.code,
        str(path),
        f"Unresolved import: {module} ({kind} file not found)",
        "Translate the missing module or update generated imports",
        severity="error",
        line=line,
    )


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = _parse_python(path)
    if tree is None:
        return set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
    return set()


def _function_signatures(path: Path) -> dict[str, _Signature]:
    tree = _parse_python(path)
    if tree is None:
        return {}
    signatures: dict[str, _Signature] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        args = [arg.arg for arg in node.args.args]
        defaults = len(node.args.defaults)
        required_count = len(args) - defaults
        signatures[node.name] = _Signature(
            line=node.lineno,
            parameters=args,
            required_parameters=args[:required_count],
        )
    return signatures


def _finding(
    code: str,
    path: str,
    message: str,
    fix: str,
    *,
    severity: Severity,
    line: int | None = None,
) -> ValidationFinding:
    return ValidationFinding(
        severity=severity,
        code=code,
        path=path,
        line=line,
        message=message,
        fix=fix,
    )
