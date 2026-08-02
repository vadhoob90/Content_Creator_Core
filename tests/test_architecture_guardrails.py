import json
import subprocess
import sys
from pathlib import Path

import content_creator
from content_creator.cli import build_parser
from content_creator.commands import perspective, voice
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
        "pack",
        "packs",
        "perspective",
        "plan",
        "provider",
        "publish",
        "reject-research",
        "run",
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
    assert modules["content_creator.orchestrator"]["line_count"] >= 800
    assert "content_creator.visuals" in modules["content_creator.orchestrator"]["imports"]


def test_maintainability_documents_are_linked_from_the_core_guide():
    core_guide = (ROOT / "docs" / "core" / "README.md").read_text(encoding="utf-8")

    for target in (
        "development-principles.md",
        "public-contracts.md",
        "../adr/0007-modular-monolith-boundaries.md",
    ):
        assert target in core_guide


def test_large_cli_families_have_dedicated_command_modules():
    assert callable(voice.run)
    assert callable(perspective.run)

    cli_path = ROOT / "src" / "content_creator" / "cli.py"
    assert len(cli_path.read_text(encoding="utf-8").splitlines()) < 1_100
