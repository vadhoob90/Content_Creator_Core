import ast
import runpy
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = runpy.run_path(str(ROOT / "scripts" / "architecture_report.py"))
READABILITY = runpy.run_path(str(ROOT / "scripts" / "readability_report.py"))


def _module(
    name: str,
    *,
    lines: int = 10,
    imports: list[str] | None = None,
    deleted: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "module": name,
        "path": "src/{}.py".format(name.replace(".", "/")),
        "line_count": lines,
        "implementation_line_count": lines,
        "imports": imports or [],
        "classes": [],
        "deleted_parameters": deleted or [],
    }


def _valid_architecture_modules() -> list[dict[str, object]]:
    return [
        _module("content_creator"),
        _module("content_creator.cli", lines=100),
        _module("content_creator.commands.runtime", lines=300),
        _module(
            "content_creator.orchestrator",
            imports=["content_creator.capabilities", "content_creator.stages"],
        ),
        _module("content_creator.voices", imports=["content_creator.versioned_artifacts"]),
        _module("content_creator.perspectives", imports=["content_creator.versioned_artifacts"]),
    ]


def test_architecture_harness_accepts_every_rule_at_its_boundary():
    violations = ARCHITECTURE["architecture_violations"]({"modules": _valid_architecture_modules()})

    assert violations == []


def test_architecture_harness_rejects_representative_weakened_boundaries():
    modules = _valid_architecture_modules()
    modules[1]["implementation_line_count"] = 101
    modules[2]["implementation_line_count"] = 301
    modules[3]["imports"] = ["content_creator.visuals"]
    modules[4]["imports"] = []
    modules.append(
        _module(
            "content_creator.oversized",
            lines=501,
            deleted=[{"function": "mutated", "parameter": "safety", "line": 12}],
        )
    )

    violations = ARCHITECTURE["architecture_violations"]({"modules": modules})

    expected_fragments = (
        "cli must remain a façade",
        "commands.runtime must remain a façade",
        "oversized exceeds the 500-line",
        "deletes parameter 'safety'",
        "orchestrator must not import content_creator.visuals",
        "orchestrator must compose content_creator.capabilities",
        "orchestrator must compose content_creator.stages",
        "content_creator.voices must use shared versioned-artifact mechanics",
    )
    assert all(
        any(fragment in violation for violation in violations) for fragment in expected_fragments
    )


def test_architecture_harness_rejects_every_edge_in_an_internal_import_cycle():
    modules = _valid_architecture_modules()
    modules.extend(
        [
            _module("content_creator.persistence", imports=["content_creator.application"]),
            _module("content_creator.application", imports=["content_creator.persistence"]),
        ]
    )

    violations = ARCHITECTURE["architecture_violations"]({"modules": modules})

    assert (
        "internal import cycle includes content_creator.application -> content_creator.persistence"
    ) in violations
    assert (
        "internal import cycle includes content_creator.persistence -> content_creator.application"
    ) in violations


def test_architecture_harness_attributes_nested_deleted_parameters_to_their_owners():
    tree = ast.parse(
        """
def outer(required, unused):
    def inner(unused):
        del unused
    del required
    return inner(unused)
"""
    )

    assert ARCHITECTURE["deleted_parameters"](tree) == [
        {"function": "outer", "parameter": "required", "line": 5},
        {"function": "inner", "parameter": "unused", "line": 4},
    ]


def test_architecture_advisories_detect_cross_file_inheritance_and_single_importers():
    modules = [
        {**_module("content_creator.protocol"), "classes": [{"name": "Provider", "bases": []}]},
        {
            **_module("content_creator.adapter", imports=["content_creator.protocol"]),
            "classes": [{"name": "OpenAIProvider", "bases": ["Provider"]}],
        },
    ]

    advisories = ARCHITECTURE["architecture_advisories"](modules)

    assert advisories["single_importer_modules"] == ["content_creator.protocol"]
    assert advisories["cross_file_inheritance"] == [
        {
            "class": "content_creator.adapter.OpenAIProvider",
            "base": "content_creator.protocol.Provider",
        }
    ]


def test_architecture_collector_parses_the_production_package():
    report = ARCHITECTURE["build_report"]()

    modules = {module["module"]: module for module in report["modules"]}
    assert report["package"] == "content_creator"
    assert "content_creator.routing" in modules
    assert "content_creator.domain" in modules["content_creator.routing"]["imports"]
    assert modules["content_creator.routing"]["path"] == "src/content_creator/routing.py"


def _readability_module(**overrides):
    values = {
        "path": Path("src/content_creator/example.py"),
        "line_count": 500,
        "implementation_line_count": 500,
        "generic_name": False,
        "generic_classes": (),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _readability_function(**overrides):
    values = {
        "path": Path("src/content_creator/example.py"),
        "name": "execute",
        "line": 1,
        "line_count": 80,
        "implementation_line_count": 80,
        "parameter_count": 7,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_readability_harness_accepts_hard_limit_boundaries():
    failures = READABILITY["violations"]([_readability_module()], [_readability_function()])

    assert failures == []


def test_readability_harness_rejects_each_hard_limit_mutation():
    modules = [
        _readability_module(implementation_line_count=501),
        _readability_module(path=Path("src/content_creator/utils.py"), generic_name=True),
        _readability_module(generic_classes=("Manager",)),
    ]
    functions = [
        _readability_function(implementation_line_count=81),
        _readability_function(name="configure", parameter_count=8),
    ]

    failures = READABILITY["violations"](modules, functions)

    expected_fragments = (
        "maximum is 500",
        "banned generic module name",
        "banned generic class name Manager",
        "maximum is 80",
        "8 parameters; maximum is 7",
    )
    assert all(any(fragment in failure for failure in failures) for fragment in expected_fragments)


def test_readability_harness_warns_at_ideal_boundaries_without_failing():
    modules = [_readability_module(implementation_line_count=301)]
    functions = [_readability_function(implementation_line_count=41)]

    warnings = READABILITY["warnings"](modules, functions)

    assert len(warnings) == 2
    assert any("300-line ideal" in warning for warning in warnings)
    assert any("40-line implementation ideal" in warning for warning in warnings)


def test_readability_collector_measures_production_scripts_and_tests():
    modules, functions = READABILITY["collect_measures"]()

    paths = {module.path.as_posix() for module in modules}
    assert "src/content_creator/routing.py" in paths
    assert "scripts/readability_report.py" in paths
    assert "tests/test_guardrail_harness.py" in paths
    assert any(function.name == "build_route" for function in functions)
