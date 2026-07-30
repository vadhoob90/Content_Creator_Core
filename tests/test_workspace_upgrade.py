import subprocess

import pytest

from content_creator.upgrade import WorkspaceUpgradeError, WorkspaceUpgrader

DEPENDENCY = (
    'dependencies = ["content-creator @ '
    'git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.5.0"]\n'
)


def _workspace(project):
    (project / "pyproject.toml").write_text(DEPENDENCY, encoding="utf-8")
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
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


@pytest.mark.parametrize("target", ["main", "release-0.6", "abc123", "v0.6"])
def test_upgrade_rejects_moving_or_ambiguous_refs(project, target):
    root = _workspace(project)
    with pytest.raises(WorkspaceUpgradeError, match="immutable"):
        WorkspaceUpgrader(root).preview(target)


def test_upgrade_applies_dependency_and_runs_validation(project):
    root = _workspace(project)
    commands = []

    def passing(command):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    report = WorkspaceUpgrader(root, runner=passing).apply("v0.6.0")

    assert report["status"] == "applied"
    assert "@v0.6.0" in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert commands[0] == ["uv", "lock", "--upgrade-package", "content-creator"]
    assert commands[-1] == ["uv", "run", "pytest"]


def test_upgrade_restores_dependency_and_lockfile_on_failure(project):
    root = _workspace(project)
    before_project = (root / "pyproject.toml").read_text(encoding="utf-8")
    before_lock = (root / "uv.lock").read_text(encoding="utf-8")

    def failing(command):
        (root / "uv.lock").write_text("changed\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

    with pytest.raises(WorkspaceUpgradeError, match="validation failed"):
        WorkspaceUpgrader(root, runner=failing).apply("v0.6.0")

    assert (root / "pyproject.toml").read_text(encoding="utf-8") == before_project
    assert (root / "uv.lock").read_text(encoding="utf-8") == before_lock


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
