"""Skeleton translator tests — config and import emission."""



from tests.translate.skeleton.helpers import (
    CFG,
    assert_valid_python,
    translate_source,
)


def test_import_map_emits_configured_python_imports_and_drops_known_imports() -> None:
    python_source, coverage = translate_source(
        """
        import java.nio.file.Path;
        import java.util.List;

        public class UsesPath {
            public Path first(List<Path> paths) {
                return paths.get(0);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from pathlib import Path" in python_source
    assert "java.util.List" not in python_source
    assert "def first(self, paths: list[Path]) -> Path:" in python_source
    assert_valid_python(python_source)





def test_custom_import_map_and_naming_flags_are_respected() -> None:
    cfg = CFG.model_copy(
        update={
            "import_map": {**CFG.import_map, "com.example.ExternalThing": "from ext import Thing"},
            "snake_case_methods": False,
            "snake_case_fields": False,
        },
    )
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class Naming {
            private String displayName = "x";

            public String getDisplayName() {
                return displayName;
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert "from ext import Thing" in python_source
    assert "self.displayName: str" in python_source
    assert "def getDisplayName(self) -> str:" in python_source
    assert "return self.displayName" in python_source
    assert_valid_python(python_source)



