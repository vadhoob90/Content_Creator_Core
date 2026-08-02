import json
import subprocess
import sys
from pathlib import Path

import content_creator
from content_creator.cli import build_parser
from content_creator.commands import operations, perspective, provider, schema, visual, voice
from content_creator.domain import WorkOrder

ROOT = Path(__file__).resolve().parents[1]


def test_public_python_exports_are_characterized():
    assert content_creator.__all__ == [
        "Orchestrator",
        "VERSION",
        "VisualAdapter",
        "VisualBrief",
        "VisualWorkflow",
        "WorkOrder",
        "__version__",
    ]


def test_top_level_cli_commands_are_characterized():
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    )

    assert set(subparsers.choices) == {
        "advanced",
        "agents",
        "approve-research",
        "coordinator",
        "diagnostics",
        "doctor",
        "eval",
        "init",
        "overview",
        "operations",
        "pack",
        "packs",
        "perspective",
        "plan",
        "provider",
        "publish",
        "reject-research",
        "run",
        "schema",
        "start",
        "status",
        "submission",
        "voice",
        "visual",
        "workspace",
    }


def test_work_order_schema_contract_is_characterized():
    schema = WorkOrder.model_json_schema()

    assert schema["required"] == ["request", "topic"]
    assert {
        "voice_id",
        "content_pack",
        "format",
        "research_depth",
        "research_source",
        "provider",
        "perspective_mode",
        "perspective_selections",
        "pack_options",
        "parent_run_id",
    } <= schema["properties"].keys()


def test_architecture_report_describes_modules_and_dependencies():
    result = subprocess.run(
        [sys.executable, "scripts/architecture_report.py", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)

    assert report["package"] == "content_creator"
    assert report["summary"]["module_count"] >= 30
    assert report["summary"]["line_count"] >= 10_000
    modules = {module["module"]: module for module in report["modules"]}
    assert modules["content_creator.orchestrator"]["line_count"] <= 500
    assert modules["content_creator.commands.runtime"]["line_count"] <= 300
    oversized = {
        name: module["line_count"] for name, module in modules.items() if module["line_count"] > 500
    }
    assert oversized == {}
    orchestrator_imports = modules["content_creator.orchestrator"]["imports"]
    assert "content_creator.capabilities" in orchestrator_imports
    assert "content_creator.stages" in orchestrator_imports
    assert "content_creator.visuals" not in orchestrator_imports
    assert "content_creator.voice_assessment" not in orchestrator_imports


def test_architecture_rules_are_enforced():
    result = subprocess.run(
        [sys.executable, "scripts/architecture_report.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_maintainability_documents_are_linked_from_the_core_guide():
    core_guide = (ROOT / "docs" / "core" / "README.md").read_text(encoding="utf-8")

    for target in (
        "development-principles.md",
        "public-contracts.md",
        "schema-compatibility.md",
        "operations-and-recovery.md",
        "architecture-guardrails.md",
        "../adr/0007-modular-monolith-boundaries.md",
        "../adr/0008-lifecycle-stages-and-capabilities.md",
        "../adr/0009-schema-governance-and-operational-recovery.md",
        "../adr/0010-module-responsibility-and-size-guardrails.md",
    ):
        assert target in core_guide


def test_large_cli_families_have_dedicated_command_modules():
    for family in (operations, perspective, provider, schema, visual, voice):
        assert callable(family.run)
    for family in (operations, perspective, provider, schema, visual, voice):
        assert callable(family.register)

    cli_path = ROOT / "src" / "content_creator" / "cli.py"
    assert len(cli_path.read_text(encoding="utf-8").splitlines()) < 1_100


def test_full_production_package_is_in_the_mypy_gate():
    configuration = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'files = ["src/content_creator"]' in configuration
    assert "disallow_untyped_defs = true" in configuration
