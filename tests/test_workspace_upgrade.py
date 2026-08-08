import json
import subprocess

import pytest

from content_creator.domain import RoutePlan, RunState, RunStatus, WorkOrder
from content_creator.storage import RunStore
from content_creator.upgrade import WorkspaceUpgradeError, WorkspaceUpgrader
from content_creator.workspace import readme_core_dependency

DEPENDENCY = (
    'dependencies = ["content-creator @ '
    'git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.5.0"]\n'
)
PINNED_GIT_DEPENDENCY = (
    "content-creator @ git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.5.0"
)


def _workspace(project):
    (project / "pyproject.toml").write_text(DEPENDENCY, encoding="utf-8")
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return project


def _managed_readme(project):
    (project / "README.md").write_text(
        "# Example\n\n"
        + readme_core_dependency("v0.5.0", PINNED_GIT_DEPENDENCY)
        + "\n\n## Custom section\n\nKeep me.\n",
        encoding="utf-8",
    )
    return project


def test_upgrade_preview_is_immutable_and_non_mutating(project):
    root = _workspace(project)
    before = (root / "pyproject.toml").read_text(encoding="utf-8")

    report = WorkspaceUpgrader(root).preview("v0.6.0")

    assert report["status"] == "preview"
    assert report["from"] == "v0.5.0"
    assert report["to"] == "v0.6.0"
    assert report["immutable_target"] is True
    assert (root / "pyproject.toml").read_text(encoding="utf-8") == before
    assert "agents/" in report["preserved"]
    assert report["compatibility"]["dependency_update"] == "preview"
    assert report["compatibility"]["workspace_readiness"] == "compatible"
    assert report["personalisation"]["inspect_command"] == ["personalisation", "show"]


@pytest.mark.parametrize("target", ["main", "release-0.6", "abc123", "v0.6"])
def test_upgrade_rejects_moving_or_ambiguous_refs(project, target):
    root = _workspace(project)
    with pytest.raises(WorkspaceUpgradeError, match="immutable"):
        WorkspaceUpgrader(root).preview(target)


def test_upgrade_applies_dependency_and_runs_validation(project):
    root = _managed_readme(_workspace(project))
    commands = []

    def passing(command):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    report = WorkspaceUpgrader(root, runner=passing).apply("v0.6.0")

    assert report["status"] == "applied"
    assert "@v0.6.0" in (root / "pyproject.toml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "@v0.6.0" in readme
    assert "Content_Creator_Core/tree/v0.6.0" in readme
    assert "## Custom section\n\nKeep me." in readme
    assert report["readme_updated"] is True
    assert "Run content-creator --workspace . personalisation show." in report["manual_follow_up"]
    assert report["compatibility"]["dependency_update"] == "applied"
    assert (root / report["compatibility_report"]).exists()
    assert commands[0] == ["uv", "lock", "--upgrade-package", "content-creator"]
    assert commands[-1] == ["uv", "run", "pytest"]


def test_upgrade_restores_dependency_and_lockfile_on_failure(project):
    root = _managed_readme(_workspace(project))
    before_project = (root / "pyproject.toml").read_text(encoding="utf-8")
    before_lock = (root / "uv.lock").read_text(encoding="utf-8")
    before_readme = (root / "README.md").read_text(encoding="utf-8")

    def failing(command):
        (root / "uv.lock").write_text("changed\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

    with pytest.raises(WorkspaceUpgradeError, match="validation failed"):
        WorkspaceUpgrader(root, runner=failing).apply("v0.6.0")

    assert (root / "pyproject.toml").read_text(encoding="utf-8") == before_project
    assert (root / "uv.lock").read_text(encoding="utf-8") == before_lock
    assert (root / "README.md").read_text(encoding="utf-8") == before_readme


def test_upgrade_does_not_rewrite_custom_readme_without_managed_block(project):
    root = _workspace(project)
    (root / "README.md").write_text("# Fully custom\n", encoding="utf-8")

    report = WorkspaceUpgrader(root).preview("v0.6.0")

    assert report["readme"]["managed_core_dependency"] is False


def test_upgrade_preserves_registry_distribution_source(project):
    (project / "pyproject.toml").write_text(
        'dependencies = ["content-creator==0.6.0"]\n',
        encoding="utf-8",
    )
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    report = WorkspaceUpgrader(project).preview("v0.6.1")

    assert report["source"] == "registry"
    assert report["from"] == "v0.6.0"
    assert report["dependency_after"] == "content-creator==0.6.1"


def test_upgrade_audit_surfaces_legacy_pack_conflict_without_mutation(project):
    root = _workspace(project)
    pack = root / "packs" / "legacy-audit"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "id": "legacy-audit",
                "version": "1.0.0",
                "extends": "general-text",
                "format": "text",
                "destination": "content/general-text/published",
                "defaults": {"banned_phrases": ["current policy"]},
            }
        ),
        encoding="utf-8",
    )
    store = RunStore(root)
    state = RunState(
        id="legacy-conflict",
        status=RunStatus.READY,
        work_order=WorkOrder(
            request="Draft",
            topic="Draft",
            content_pack="legacy-audit",
            pack_options={"banned_phrases": ["old policy"]},
        ),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
    )
    store.create(state)
    before = (store.run_dir(state.id) / "state.json").read_text(encoding="utf-8")

    report = WorkspaceUpgrader(root).preview("v0.6.0")["compatibility"]

    finding = next(item for item in report["historical_runs"] if item["run_id"] == state.id)
    assert finding["outcome"] == "decision_required"
    assert finding["publication_blocked"] is True
    assert report["decision_prompts"][0]["differences"][0] == {
        "setting": "banned_phrases",
        "legacy_value": ["old policy"],
        "current_value": ["current policy"],
        "outcome": "conflict",
        "effective_source": "current_pack",
    }
    assert (store.run_dir(state.id) / "state.json").read_text(encoding="utf-8") == before


def test_upgrade_audit_reports_compatible_legacy_override(project):
    root = _workspace(project)
    pack = root / "packs" / "legacy-audit"
    pack.mkdir()
    policy = ["current policy"]
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "id": "legacy-audit",
                "version": "1.0.0",
                "extends": "general-text",
                "format": "text",
                "destination": "content/general-text/published",
                "defaults": {"banned_phrases": policy},
            }
        ),
        encoding="utf-8",
    )
    RunStore(root).create(
        RunState(
            id="legacy-compatible",
            status=RunStatus.READY,
            work_order=WorkOrder(
                request="Draft",
                topic="Draft",
                content_pack="legacy-audit",
                pack_options={"banned_phrases": policy},
            ),
            route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
        )
    )

    report = WorkspaceUpgrader(root).preview("v0.6.0")["compatibility"]

    assert report["counts"]["automatically_migrated"] == 1
    assert report["historical_run_compatibility"] == "automatically_migrated"


def test_applied_upgrade_persists_run_migration_visibility(project):
    root = _workspace(project)
    pack = root / "packs" / "legacy-audit"
    pack.mkdir()
    policy = ["current policy"]
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "id": "legacy-audit",
                "version": "1.0.0",
                "extends": "general-text",
                "format": "text",
                "destination": "content/general-text/published",
                "defaults": {"banned_phrases": policy},
            }
        ),
        encoding="utf-8",
    )
    store = RunStore(root)
    store.create(
        RunState(
            id="visible-migration",
            status=RunStatus.READY,
            work_order=WorkOrder(
                request="Draft",
                topic="Draft",
                content_pack="legacy-audit",
                pack_options={"banned_phrases": policy},
            ),
            route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
        )
    )

    report = WorkspaceUpgrader(
        root,
        runner=lambda command: subprocess.CompletedProcess(command, 0, stdout="ok", stderr=""),
    ).apply("v0.6.0")

    state = store.load("visible-migration")
    assert (store.run_dir(state.id) / "pack-migration.json").exists()
    assert any(event.name == "legacy_pack_options_resolved" for event in state.events)
    assert (root / report["compatibility_report"]).exists()
