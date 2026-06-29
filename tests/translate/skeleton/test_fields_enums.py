"""Skeleton translator tests — fields, enums, and type declarations."""

from pathlib import Path

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from j2py.validate.checks import validate_source
from scripts.corpus.corpus_presets import corpus_checkout_root
from tests.translate.skeleton.helpers import (
    CFG,
    FIXTURES,
    assert_valid_python,
    translate_source,
    translate_source_with_diagnostics,
)


def assert_validated_python(source: str) -> None:
    result = validate_source(source)
    assert result.ok, result.syntax_errors + result.ruff_errors + result.mypy_errors


def test_field_without_constructor_assignment_uses_java_default() -> None:
    python_source, coverage = translate_source("public class FieldOnly { private int count; }")

    assert coverage == 1.0
    assert "self.count: int = 0" in python_source
    assert_valid_python(python_source)


def test_uninitialized_field_defaults_use_java_semantics() -> None:
    python_source, coverage = translate_source(
        """
        public class Defaults {
            private int count;
            private long total;
            private double ratio;
            private boolean enabled;
            private char marker;
            private String name;
            private int[] values;
            private static boolean ready;
        }
        """,
    )

    assert coverage == 1.0
    assert "ready: bool = False" in python_source
    assert "self.count: int = 0" in python_source
    assert "self.total: int = 0" in python_source
    assert "self.ratio: float = 0.0" in python_source
    assert "self.enabled: bool = False" in python_source
    assert 'self.marker: str = "\\0"' in python_source
    assert "self.name: str | None = None" in python_source
    assert "self.values: list[int] | None = None" in python_source
    assert "TODO(j2py): verify default value" not in python_source
    assert_valid_python(python_source)


def test_bean_validation_annotations_lower_to_pydantic_fields() -> None:
    parsed = parse_file(FIXTURES / "java" / "PydanticValidation.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.source == (FIXTURES / "python" / "PydanticValidation.py").read_text()
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_jpa_entity_lowers_to_sqlalchemy_declarative_model() -> None:
    parsed = parse_file(FIXTURES / "java" / "SqlAlchemyEntity.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.source == (FIXTURES / "python" / "SqlAlchemyEntity.py").read_text()
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "def get_address" not in result.source
    assert "def set_address" not in result.source
    assert "def get_owner" not in result.source
    assert_valid_python(result.source)


def test_spring_data_repository_lowers_to_session_backed_class() -> None:
    parsed = parse_file(FIXTURES / "java" / "SpringDataRepository.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.source == (FIXTURES / "python" / "SpringDataRepository.py").read_text()
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from sqlalchemy import func, select" in result.source
    assert "from sqlalchemy.orm import Session" in result.source
    assert "class OwnerRepository:" in result.source
    assert "Protocol" not in result.source
    assert "return self._session.get(Owner, id)" in result.source
    assert "return list(self._session.execute(select(Owner)).scalars())" in result.source
    assert "self._session.add(entity)" in result.source
    assert "self._session.delete(entity)" in result.source
    assert "# JPQL: SELECT o FROM Owner o WHERE o.lastName = :lastName" in result.source
    assert "raise NotImplementedError" in result.source
    assert_valid_python(result.source)


def test_spring_data_repository_respects_disabled_type_hints() -> None:
    cfg = CFG.model_copy(update={"emit_type_hints": False})
    parsed = parse_file(FIXTURES / "java" / "SpringDataRepository.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), cfg)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from sqlalchemy import func, select" in result.source
    assert "from sqlalchemy.orm import Session" not in result.source
    assert "def __init__(self, session):" in result.source
    assert "def find_by_last_name(self, last_name):" in result.source
    assert "def find_by_id(self, id):" in result.source
    assert " -> " not in result.source
    assert_valid_python(result.source)


def test_spring_data_repository_skips_malformed_generic_base() -> None:
    result = translate_source_with_diagnostics(
        """
        class Owner {}

        interface OwnerRepository extends Repository<>, JpaRepository<Owner, Integer> {
        }
        """
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class OwnerRepository:" in result.source
    assert "class OwnerRepository(Protocol):" not in result.source
    assert "def find_by_id(self, id: int) -> Owner | None:" in result.source
    assert_valid_python(result.source)


def test_bean_validation_entity_is_not_promoted_to_pydantic_model() -> None:
    result = translate_source_with_diagnostics(
        """
        @Entity
        class Owner {
            @NotNull
            private String name;
        }
        """,
    )

    assert "from pydantic" not in result.source
    assert "class Owner(BaseModel):" not in result.source
    assert "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column" in result.source
    assert "class Owner(Base):" in result.source
    assert '__tablename__ = "owner"' in result.source
    assert "name: Mapped[str] = mapped_column(String, nullable=False)" in result.source
    assert_valid_python(result.source)


def test_jpa_entity_default_nullable_column_uses_optional_annotation() -> None:
    result = translate_source_with_diagnostics(
        """
        @Entity
        class Owner {
            @Column
            private String nickname;
        }
        """,
    )

    assert "nickname: Mapped[str | None] = mapped_column(String)" in result.source
    assert_valid_python(result.source)


def test_jpa_relationship_join_column_infers_external_target() -> None:
    result = translate_source_with_diagnostics(
        """
        @Entity
        class Pet {
            @ManyToOne
            @JoinColumn(name = "owner_id")
            private Owner owner;
        }
        """,
    )

    assert 'owner_id: Mapped[int] = mapped_column(ForeignKey("owner.id"))' in result.source
    assert "owner: Mapped[Owner] = relationship()" in result.source
    assert "Mapped[list[Owner]]" not in result.source
    assert_valid_python(result.source)


def test_jpa_relationship_cascade_constants_map_to_sqlalchemy_names() -> None:
    result = translate_source_with_diagnostics(
        """
        @Entity
        class Owner {
            @OneToMany(cascade = {CascadeType.PERSIST, CascadeType.REMOVE}, mappedBy = "owner")
            private List<Pet> pets;
        }
        """,
    )

    assert 'relationship(back_populates="owner", cascade="save-update, delete")' in result.source
    assert "pets: Mapped[list[Pet]]" in result.source
    assert_valid_python(result.source)


def test_bean_validation_subclass_is_not_promoted_to_pydantic_model() -> None:
    result = translate_source_with_diagnostics(
        """
        class PersonForm extends BaseForm {
            @NotNull
            private String name;
        }
        """,
    )

    assert "from pydantic" not in result.source
    assert "class PersonForm(BaseForm):" in result.source
    assert "self.name: str | None = None" in result.source
    assert_valid_python(result.source)


def test_pydantic_model_field_initializer_is_translated_once() -> None:
    result = translate_source_with_diagnostics(
        """
        class MixedValidation {
            @NotNull
            private String name;
            private Runnable callback = () -> { System.out.println("ok"); };
        }
        """,
    )

    assert "class MixedValidation(BaseModel):" in result.source
    assert "name: str = Field(...)" in result.source
    assert result.source.count("def _j2py_lambda_") == 1
    assert "callback: Runnable = _j2py_lambda_1" in result.source
    assert_valid_python(result.source)


def test_instance_field_initializer_can_reference_another_field() -> None:
    python_source, coverage = translate_source(
        """
        public class FieldRefs {
            private int base = 1;
            private int copy = base;
        }
        """,
    )

    assert coverage == 1.0
    assert "self.base: int = 1" in python_source
    assert "self.copy: int = self.base" in python_source
    assert "self.copy: int = base" not in python_source
    assert_valid_python(python_source)


def test_static_initializer_block_populates_class_collection() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.HashSet;
        import java.util.Set;

        public class StaticInit {
            private static Set<String> NAMES = new HashSet<>();
            static {
                NAMES.add("alpha");
                NAMES.add("beta");
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "unsupported class member block" not in result.source
    assert "NAMES: set[str] = set()" in result.source
    assert 'NAMES.add("alpha")' in result.source
    assert 'NAMES.add("beta")' in result.source
    assert result.source.index("NAMES: set[str] = set()") < result.source.index(
        'NAMES.add("alpha")',
    )
    assert_valid_python(result.source)


def test_static_initializer_preserves_order_with_static_fields() -> None:
    result = translate_source_with_diagnostics(
        """
        public class StaticOrder {
            private static int count = 1;
            static {
                count += 2;
            }
            private static int after = count;
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    count_index = result.source.index("count: int = 1")
    increment_index = result.source.index("count += 2")
    after_index = result.source.index("after: int = count")
    assert count_index < increment_index < after_index
    assert_valid_python(result.source)


def test_static_initializer_block_lambda_emits_helper_before_use() -> None:
    result = translate_source_with_diagnostics(
        """
        public class StaticInitializerLambda {
            private static Runnable task;

            static {
                task = () -> { System.out.println("ready"); };
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "def _j2py_lambda_1()" in result.source
    assert "task = _j2py_lambda_1" in result.source
    assert result.source.index("def _j2py_lambda_1(") < result.source.index(
        "task = _j2py_lambda_1",
    )
    assert_valid_python(result.source)


def test_instance_initializer_block_runs_before_constructor_body() -> None:
    result = translate_source_with_diagnostics(
        """
        public class InstanceInit {
            private int count = 1;
            {
                count += 2;
            }

            public InstanceInit() {
                count += 3;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "unsupported class member block" not in result.source
    field_index = result.source.index("self.count: int = 1")
    initializer_index = result.source.index("self.count += 2")
    constructor_index = result.source.index("self.count += 3")
    assert field_index < initializer_index < constructor_index
    assert_valid_python(result.source)


def test_instance_initializer_block_lambda_emits_helper_before_use() -> None:
    result = translate_source_with_diagnostics(
        """
        public class InstanceInitializerLambda {
            private Runnable task;

            {
                task = () -> { System.out.println("ready"); };
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "def _j2py_lambda_1()" in result.source
    assert "self.task = _j2py_lambda_1" in result.source
    assert result.source.index("def _j2py_lambda_1(") < result.source.index(
        "self.task = _j2py_lambda_1",
    )
    assert_valid_python(result.source)


def test_anonymous_class_method_can_emit_nested_block_lambda_helper() -> None:
    result = translate_source_with_diagnostics(
        """
        public class AnonymousHelpers {
            interface Maker {
                Runnable make(String prefix);
            }

            public Maker maker() {
                return new Maker() {
                    @Override
                    public Runnable make(String prefix) {
                        return () -> {
                            System.out.println(prefix);
                        };
                    }
                };
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class _J2pyAnonymous1(AnonymousHelpers.Maker):" in result.source
    assert "def make(self, prefix: str) -> Runnable:" in result.source
    assert "def _j2py_lambda_1()" in result.source
    assert "print(prefix)" in result.source
    assert "return _j2py_lambda_1" in result.source
    assert result.source.index("def _j2py_lambda_1(") < result.source.index(
        "return _j2py_lambda_1",
    )
    assert_valid_python(result.source)


def test_anonymous_class_instance_field_translates_to_helper_init() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.concurrent.Callable;

        public class TaskFactory {
            public Callable<String> makeTask(final String prefix) {
                return new Callable<String>() {
                    private int counter = 0;

                    @Override
                    public String call() {
                        counter++;
                        return prefix + "-" + counter;
                    }
                };
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "def __init__(self):" in result.source
    assert "self.counter: int = 0" in result.source
    assert "self.counter += 1" in result.source
    assert_valid_python(result.source)


def test_anonymous_class_static_field_translates_to_helper_class_attr() -> None:
    result = translate_source_with_diagnostics(
        """
        public class AnonymousStaticField {
            public Object make() {
                return new Object() {
                    private static final long serialVersionUID = 1L;
                };
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "unsupported anonymous class static field" not in result.source
    assert "class _J2pyAnonymous1:" in result.source
    assert "serial_version_uid: int = 1" in result.source
    assert_valid_python(result.source)


def test_anonymous_class_member_block_translates_to_helper_init() -> None:
    result = translate_source_with_diagnostics(
        """
        public abstract class AnonymousInitializer {
            public Object make() {
                return new Object() {
                    private boolean ready;

                    {
                        ready = true;
                        configure(false);
                    }

                    public void configure(boolean value) {
                        ready = value;
                    }
                };
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "unsupported anonymous class member block" not in result.source
    assert "def __init__(self):" in result.source
    assert "self.ready: bool = False" in result.source
    assert "self.ready = True" in result.source
    assert "self.configure(False)" in result.source
    assert result.source.index("self.ready: bool = False") < result.source.index(
        "self.ready = True",
    )
    assert_valid_python(result.source)


def test_static_field_anonymous_class_translates_with_local_helper() -> None:
    result = translate_source_with_diagnostics(
        """
        public abstract class Ticker {
            private static final Ticker SYSTEM_TICKER = new Ticker() {
                @Override
                public long read() {
                    return System.nanoTime();
                }
            };

            public abstract long read();
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class _J2pyAnonymous1(Ticker):" in result.source
    assert "SYSTEM_TICKER: Ticker = _J2pyAnonymous1()" in result.source
    assert result.source.index("class _J2pyAnonymous1(Ticker):") < result.source.index(
        "SYSTEM_TICKER: Ticker = _J2pyAnonymous1()",
    )
    assert_valid_python(result.source)


def test_static_field_anonymous_subclass_of_outer_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        public abstract class NopHandler {
            public final static NopHandler instance = new NopHandler() {
                @Override
                public String name() {
                    return "nop";
                }
            };

            public abstract String name();
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class _J2pyAnonymous1(NopHandler):" in result.source
    assert "instance: NopHandler = _J2pyAnonymous1()" in result.source
    assert_valid_python(result.source)


def test_anonymous_and_inner_corpus_construct_reaches_full_coverage() -> None:
    parsed = parse_file(FIXTURES / "corpus" / "constructs" / "AnonymousAndInner.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_enum_constant_class_body_reaches_full_coverage() -> None:
    parsed = parse_file(FIXTURES / "corpus" / "constructs" / "EnumConstantClassBody.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class _J2pyEnumConstantEXPLICIT:" in result.source
    assert "_EnumConstantClassBody_j2py_enum_bodies" in result.source
    assert "return False" in result.source
    assert "return True" in result.source
    assert "return body_cls.was_evicted(self)" in result.source
    assert "_J2PY_ENUM_BODY_BY_NAME" not in result.source
    assert "@abstractmethod" not in result.source
    assert_valid_python(result.source)


def test_enum_constant_class_body_runs_at_runtime() -> None:
    parsed = parse_file(FIXTURES / "corpus" / "constructs" / "EnumConstantClassBody.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    namespace: dict[str, object] = {}
    exec(compile(result.source, "<translated>", "exec"), namespace)
    enum_cls = namespace["EnumConstantClassBody"]
    assert enum_cls.EXPLICIT.was_evicted() is False
    assert enum_cls.REPLACED.was_evicted() is False
    assert enum_cls.COLLECTED.was_evicted() is True


def test_enum_constant_class_body_dispatches_method_arguments() -> None:
    result = translate_source_with_diagnostics(
        """
        public enum Scored {
            HIGH {
                @Override
                public int score(int base) {
                    return base + 10;
                }
            };
            public abstract int score(int base);
        }
        """,
    )

    assert result.coverage == 1.0
    assert "def score(self, base: int)" in result.source
    assert "return body_cls.score(self, base)" in result.source
    namespace: dict[str, object] = {}
    exec(compile(result.source, "<translated>", "exec"), namespace)
    assert namespace["Scored"].HIGH.score(5) == 15


def test_enum_constant_class_body_synthesizes_interface_method_dispatcher() -> None:
    result = translate_source_with_diagnostics(
        """
        interface Matcher {
            boolean matches(String value);
        }

        public enum Token implements Matcher {
            LETTER {
                @Override
                public boolean matches(String value) {
                    return value.equals("a");
                }
            };
        }
        """,
    )

    assert result.coverage == 1.0
    assert "def matches(self, value: str)" in result.source
    assert "return body_cls.matches(self, value)" in result.source
    namespace: dict[str, object] = {}
    exec(compile(result.source, "<translated>", "exec"), namespace)
    assert namespace["Token"].LETTER.matches("a") is True
    assert namespace["Token"].LETTER.matches("b") is False


def test_enum_direct_declarations_do_not_capture_nested_type_members() -> None:
    result = translate_source_with_diagnostics(
        """
        public enum Outer {
            ONE("outer");

            private final String outerName;

            Outer(String outerName) {
                this.outerName = outerName;
            }

            public String label() {
                return outerName;
            }

            static class Nested {
                private final String nestedName;

                Nested(String nestedName) {
                    this.nestedName = nestedName;
                }

                public String label() {
                    return nestedName;
                }
            }
        }
        """,
    )

    assert "outer_name: str" in result.source
    assert "self.outer_name = outer_name" in result.source
    assert "return self.outer_name" in result.source
    assert "nested_name: str" not in result.source
    assert "self.nested_name" not in result.source
    assert_valid_python(result.source)


def test_enum_interface_names_skip_generic_type_arguments() -> None:
    result = translate_source_with_diagnostics(
        """
        public enum Mode implements Comparable<Mode>, Labelled {
            FAST;
        }
        """,
    )

    assert "# implements Comparable, Labelled" in result.source
    assert "# implements Comparable, Mode, Labelled" not in result.source
    assert_valid_python(result.source)


def test_super_constructor_invocation_and_base_class_translate() -> None:
    python_source, coverage = translate_source(
        """
        public class Child extends Parent {
            public Child(String name) {
                super(name);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "class Child(Parent):" in python_source
    assert "super().__init__(name)" in python_source
    assert_valid_python(python_source)


def test_block_lambda_in_field_initializer_emits_local_helper_in_init() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.function.Function;

        public class FieldLambda {
            private Function<String, String> mapper = s -> { return s.trim(); };
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "def _j2py_lambda_1(s):" in result.source
    assert "self.mapper: Callable[str, str] = _j2py_lambda_1" in result.source
    assert result.source.index("def _j2py_lambda_1(") < result.source.index(
        "self.mapper: Callable[str, str] = _j2py_lambda_1",
    )
    assert_valid_python(result.source)


def test_grouping_by_in_field_initializer_emits_local_helper_in_init() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.Map;
        import java.util.stream.Collectors;

        public class FieldStream {
            private Map<String, List<String>> groups = items.stream()
                    .collect(Collectors.groupingBy(s -> s.substring(0, 1)));
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "def _j2py_groupby_1(source):" in result.source
    assert "self.groups: dict[str, list[str]] = _j2py_groupby_1(items)" in result.source
    assert result.source.index("def _j2py_groupby_1(") < result.source.index(
        "self.groups: dict[str, list[str]] = _j2py_groupby_1(items)",
    )
    assert_valid_python(result.source)


def test_interface_declaration_translates_to_protocol() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface Greeter {
            void greet();
        }
        """,
    )

    assert result.coverage == 1.0
    assert "from typing import Protocol" in result.source
    assert "class Greeter(Protocol):" in result.source
    assert "def greet(self) -> None: ..." in result.source
    assert not result.diagnostics.unhandled
    assert [diagnostic.node_type for diagnostic in result.diagnostics.handled] == [
        "interface_declaration",
        "method_declaration",
    ]
    assert_valid_python(result.source)


def test_multiple_generic_interfaces_share_one_type_var_declaration() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface First<T> {
            void first(T value);
        }

        interface Second<T> {
            void second(T value);
        }
        """,
    )

    assert result.coverage == 1.0
    assert result.source.count('T = TypeVar("T", contravariant=True)') == 1
    assert "class First(Protocol[T]):" in result.source
    assert "class Second(Protocol[T]):" in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_conflicting_variance_interfaces_get_distinct_type_vars() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface Producer<T> {
            T get();
        }

        interface Sink<T> {
            void put(T value);
        }
        """,
    )

    assert result.coverage == 1.0
    assert 'ProducerT = TypeVar("ProducerT", covariant=True)' in result.source
    assert 'SinkT = TypeVar("SinkT", contravariant=True)' in result.source
    assert "class Producer(Protocol[ProducerT]):" in result.source
    assert "class Sink(Protocol[SinkT]):" in result.source
    assert "def get(self) -> ProducerT: ..." in result.source
    assert "def put(self, value: SinkT) -> None: ..." in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_producer_generic_interface_type_var_is_covariant() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface Box<T> {
            T get();
        }
        """,
    )

    assert result.coverage == 1.0
    assert 'T = TypeVar("T", covariant=True)' in result.source
    assert "class Box(Protocol[T]):" in result.source
    assert "def get(self) -> T: ..." in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_optional_return_generic_interface_type_var_is_covariant() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.Optional;

        public interface MaybeBox<T> {
            Optional<T> get();
        }
        """,
    )

    assert result.coverage == 1.0
    assert 'T = TypeVar("T", covariant=True)' in result.source
    assert "class MaybeBox(Protocol[T]):" in result.source
    assert "def get(self) -> T | None: ..." in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_optional_parameter_generic_interface_type_var_is_contravariant() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.Optional;

        public interface MaybeSink<T> {
            void put(Optional<T> value);
        }
        """,
    )

    assert result.coverage == 1.0
    assert 'T = TypeVar("T", contravariant=True)' in result.source
    assert "class MaybeSink(Protocol[T]):" in result.source
    assert "def put(self, value: T | None) -> None: ..." in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_mixed_generic_interface_type_var_is_invariant() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface Box<T> {
            T get();
            void put(T value);
        }
        """,
    )

    assert result.coverage == 1.0
    assert 'T = TypeVar("T")' in result.source
    assert 'T = TypeVar("T",' not in result.source
    assert "class Box(Protocol[T]):" in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_empty_generic_marker_interface_type_var_is_covariant() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface Marker<T> {
        }
        """,
    )

    assert result.coverage == 1.0
    assert 'T = TypeVar("T", covariant=True)' in result.source
    assert "class Marker(Protocol[T]):" in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_method_type_parameter_shadows_remapped_interface_type_parameter() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface Producer<T> {
            T get();
            default <T> T identity(T value) {
                return value;
            }
        }

        interface Sink<T> {
            void put(T value);
        }
        """,
    )

    assert result.coverage == 1.0
    assert 'ProducerT = TypeVar("ProducerT", covariant=True)' in result.source
    assert 'T = TypeVar("T")' in result.source
    assert "class Producer(Protocol[ProducerT]):" in result.source
    assert "def get(self) -> ProducerT: ..." in result.source
    assert "def identity(self, value: T) -> T:" in result.source
    assert not result.diagnostics.unhandled
    assert_validated_python(result.source)


def test_interface_static_factories_return_adapter_instances() -> None:
    parsed = parse_file(FIXTURES / "corpus" / "constructs" / "InterfaceDefaults.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from j2py_runtime import Consumer" in result.source
    assert "from typing import Protocol, TypeVar, cast" in result.source
    assert 'T = TypeVar("T", contravariant=True)' in result.source
    assert 'U = TypeVar("U")' in result.source
    assert "class InterfaceDefaults(Protocol[T]):" in result.source
    assert "class _NoopInterfaceDefaultsAdapter:" in result.source
    assert "class _LoggingInterfaceDefaultsAdapter:" in result.source
    assert "return cast(InterfaceDefaults[U], _NoopInterfaceDefaultsAdapter())" in result.source
    assert "return cast(InterfaceDefaults[U], _LoggingInterfaceDefaultsAdapter())" in result.source
    assert "delegate.accept(value)" in result.source
    assert "def _j2py_lambda_" not in result.source
    assert any(
        diagnostic.reason == "translated interface static factory adapter"
        for diagnostic in result.diagnostics.handled
    )
    assert_valid_python(result.source)


def test_interface_static_factory_adapter_fixture_is_not_name_specific() -> None:
    parsed = parse_file(
        FIXTURES / "corpus" / "constructs" / "InterfaceStaticFactoryAdapter.java",
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class InterfaceStaticFactoryAdapter(Protocol[T]):" in result.source
    assert "class _EmptyInterfaceStaticFactoryAdapterAdapter:" in result.source
    assert "return cast(\n            InterfaceStaticFactoryAdapter[U]," in result.source
    assert "            _EmptyInterfaceStaticFactoryAdapterAdapter()," in result.source
    assert "def _j2py_lambda_" not in result.source
    assert_valid_python(result.source)


def test_sealed_interface_preserves_permits_and_nested_permitted_types() -> None:
    parsed = parse_file(FIXTURES / "corpus" / "constructs" / "SealedClasses.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class SealedClasses(Protocol):" in result.source
    assert "# sealed: permits Success, Failure, Pending" in result.source
    assert "@dataclass(frozen=True)\n    class Success:" in result.source
    assert "@dataclass(frozen=True)\n    class Failure:" in result.source
    assert "class Pending:" in result.source
    assert "# final" in result.source
    assert "class ExtendedPending(Pending):" in result.source
    assert "# non-sealed" in result.source
    assert (
        "SealedClassesPermitted = Success | Failure | Pending  # sealed permitted subclasses"
    ) in result.source
    assert_valid_python(result.source)


def test_anonymous_class_captures_qualified_outer_this() -> None:
    parsed = parse_file(FIXTURES / "java" / "OuterThisCapture.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "_outer_self = self" in result.source
    assert "print(_outer_self.name)" in result.source
    assert "_outer_self.process()" in result.source
    assert "def __init__(self, _outer_self: object) -> None:" in result.source
    assert "self._outer_self = _outer_self" in result.source
    assert "return self._outer_self.name" in result.source
    assert "return self.InnerTask(self)" in result.source
    assert "OuterThisCapture.self" not in result.source
    assert "verify captured outer this references" not in {
        warning.reason for warning in result.diagnostics.warnings
    }
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_marker_to_dataclass() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Marker {
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "@dataclass(frozen=True)" in result.source
    assert "class Marker:" in result.source
    assert "    pass" in result.source
    assert "annotation type declaration requires manual translation" not in result.source
    assert_valid_python(result.source)


def test_annotation_type_declaration_preserves_javadoc_and_comments() -> None:
    result = translate_source_with_diagnostics(
        """
        /**
         * Describes an endpoint.
         */
        public @interface Endpoint {
            // Reviewers should still see body comments.
            String value();
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert '"""Describes an endpoint."""' in result.source
    assert "    # Reviewers should still see body comments." in result.source
    assert "value: str" in result.source
    assert any(warning.reason == "preserved comment" for warning in result.diagnostics.warnings)
    assert_valid_python(result.source)


def test_annotation_type_declaration_preserves_non_meta_annotation_comment() -> None:
    result = translate_source_with_diagnostics(
        """
        @Component("worker")
        public @interface WorkerBinding {
            String value();
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert '# @Component("worker")' in result.source
    assert "class WorkerBinding:" in result.source
    assert any(
        "preserved annotation @Component" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_elements_and_defaults() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Description {
            String value() default "";
            int count() default 0;
            boolean enabled() default true;
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert 'value: str = ""' in result.source
    assert "count: int = 0" in result.source
    assert "enabled: bool = True" in result.source
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_required_element_without_default() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface RequiredDescription {
            String value();
            int order();
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "value: str" in result.source
    assert "order: int" in result.source
    assert "value: str =" not in result.source
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_array_and_class_elements() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface RequestMapping {
            String[] value() default {};
            Class<?>[] types() default {};
            Class<?> type() default Object.class;
        }
        """,
    )

    assert result.coverage == 1.0
    assert "value: tuple[str, ...] = ()" in result.source
    assert "types: tuple[type[Any], ...] = ()" in result.source
    assert "type_: type[Any] = object" in result.source
    assert not any(
        item.reason == "annotation type declaration requires manual translation"
        for item in result.diagnostics.unhandled
    )
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_scalar_array_defaults() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Profiles {
            String[] single() default {"dev"};
            String[] many() default {"dev", "test"};
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert 'single: tuple[str, ...] = ("dev",)' in result.source
    assert 'many: tuple[str, ...] = ("dev", "test")' in result.source
    assert_valid_python(result.source)


def test_annotation_type_declaration_warns_for_non_object_class_literal_default() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Typed {
            Class<?> value() default String.class;
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "value: type[Any] = String" in result.source
    assert any(
        warning.reason == "annotation class literal default requires manual review"
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_expression_default() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Flags {
            int mask() default 1 + 2;
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "mask: int = 1 + 2" in result.source
    assert_valid_python(result.source)


def test_annotation_type_declaration_preserves_meta_annotations_as_warnings() -> None:
    result = translate_source_with_diagnostics(
        """
        @Target(ElementType.METHOD)
        @Retention(RetentionPolicy.RUNTIME)
        @Documented
        public @interface ManagedOperation {
            String description() default "";
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert 'description: str = ""' in result.source
    assert any(
        "preserved meta-annotation @Target" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert any(
        "preserved meta-annotation @Retention" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_annotation_type_declaration_applies_static_import_aliases_to_meta_comments() -> None:
    result = translate_source_with_diagnostics(
        """
        import static java.lang.annotation.ElementType.CONSTRUCTOR;
        import static java.lang.annotation.ElementType.METHOD;
        import static java.lang.annotation.ElementType.TYPE;

        import java.lang.annotation.Target;

        @Target({METHOD, CONSTRUCTOR, TYPE})
        public @interface StaticImportEnumConstants {
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "# @Target({ElementType.METHOD, ElementType.CONSTRUCTOR, ElementType.TYPE})" in (
        result.source
    )
    assert "TODO(j2py): static import" not in result.source
    assert "ElementType.ElementType" not in result.source
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_constants() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface WithConstant {
            int CONSTANT = 1;
            String DEFAULT_NAME = "item";
            String value() default DEFAULT_NAME;
        }
        """,
    )

    assert result.coverage == 1.0
    assert "class WithConstant:" in result.source
    assert "CONSTANT: ClassVar[int] = 1" in result.source
    assert 'DEFAULT_NAME: ClassVar[str] = "item"' in result.source
    assert "value: str = DEFAULT_NAME" in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_annotation_type_declaration_translates_nested_helper_class() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface WithHelper {
            String DEFAULT_NAME = "item";
            String value() default DEFAULT_NAME;

            public class Value {
                public final String name;
                public Value(String name) {
                    this.name = name;
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert 'DEFAULT_NAME: ClassVar[str] = "item"' in result.source
    assert "value: str = DEFAULT_NAME" in result.source
    assert "class Value:" in result.source
    assert "def __init__(self, name: str) -> None:" in result.source
    assert "self.name = name" in result.source
    assert "unsupported annotation member" not in result.source
    assert_valid_python(result.source)


def test_annotation_element_default_failure_is_member_level_only() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Broken {
            Broken[] nested() default { @Broken };
        }
        """,
    )

    assert "@dataclass(frozen=True)" in result.source
    assert "class Broken:" in result.source
    assert not any(
        item.node_type == "annotation_type_declaration" for item in result.diagnostics.unhandled
    )
    assert any(
        item.reason == "unsupported annotation element default"
        for item in result.diagnostics.unhandled
    )
    assert_valid_python(result.source)


def test_annotation_elements_without_type_hints_keep_defaults_and_todos() -> None:
    cfg = CFG.model_copy(update={"emit_type_hints": False})
    result = translate_source_with_diagnostics(
        """
        public @interface Compact {
            String required();
            String value() default "compact";
            Compact[] nested() default { @Compact };
        }
        """,
        cfg=cfg,
    )

    assert "required\n" in result.source
    assert 'value = "compact"' in result.source
    assert "nested = None  # TODO(j2py): unsupported default" in result.source
    assert "required: str" not in result.source
    assert any(
        item.reason == "unsupported annotation element default"
        for item in result.diagnostics.unhandled
    )
    assert_valid_python(result.source)


def test_annotation_element_with_alias_for_modifiers_translates_default() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Component {
            String value() default "";
        }

        public @interface Controller {
            @AliasFor(annotation = Component.class)
            String value() default "";
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert 'value: str = ""' in result.source
    assert not any(
        "unsupported expression modifiers" in item.reason for item in result.diagnostics.unhandled
    )
    assert any(
        "preserved annotation element @AliasFor" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def _spring_corpus_root() -> Path:
    return corpus_checkout_root() / "spring-framework"


def _skip_missing_spring_corpus(corpus_root: Path) -> None:
    import pytest

    pytest.skip(
        "Spring corpus clone not available at "
        f"{corpus_root}; run make corpus-clone-all or set J2PY_CORPUS_ROOT"
    )


def test_spring_stereotype_annotations_reach_full_coverage() -> None:
    corpus_root = _spring_corpus_root()
    if not corpus_root.is_dir():
        _skip_missing_spring_corpus(corpus_root)

    for relative in (
        "spring-context/src/main/java/org/springframework/stereotype/Controller.java",
        "spring-context/src/main/java/org/springframework/stereotype/Service.java",
    ):
        parsed = parse_file(corpus_root / relative)
        result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)
        assert result.coverage == 1.0, relative
        assert not result.diagnostics.unhandled, relative
        assert_valid_python(result.source)


def test_spring_managed_resource_alias_for_elements_translate() -> None:
    corpus_root = _spring_corpus_root()
    if not corpus_root.is_dir():
        _skip_missing_spring_corpus(corpus_root)

    path = corpus_root / (
        "spring-context/src/main/java/org/springframework/jmx/export/annotation/"
        "ManagedResource.java"
    )
    parsed = parse_file(path)
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert 'value: str = ""' in result.source
    assert 'object_name: str = ""' in result.source
    assert "currency_time_limit: int = -1" in result.source
    assert_valid_python(result.source)
