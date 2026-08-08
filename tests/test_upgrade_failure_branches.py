import subprocess

import pytest

from content_creator.domain import RoutePlan, RunEvent, RunState, RunStatus, WorkOrder
from content_creator.storage import RunStore
from content_creator.upgrade import WorkspaceUpgradeError, WorkspaceUpgrader
from content_creator.upgrade_audit import UpgradeCompatibilityAudit

DEPENDENCY = (
    'dependencies = ["content-creator @ '
    'git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.5.0"]\n'
)


def test_upgrade_preview_rejects_missing_workspace_manifest(tmp_path):
    with pytest.raises(WorkspaceUpgradeError, match="Missing workspace pyproject"):
        WorkspaceUpgrader(tmp_path).preview("v0.6.0")


def test_upgrade_preview_rejects_unpinned_dependency(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        'dependencies = ["content-creator"]\n', encoding="utf-8"
    )

    with pytest.raises(WorkspaceUpgradeError, match="does not contain a pinned"):
        WorkspaceUpgrader(tmp_path).preview("v0.6.0")


def test_failed_upgrade_removes_new_lockfile_and_preserves_absent_readme(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(DEPENDENCY, encoding="utf-8")

    def failing(command):
        (tmp_path / "uv.lock").write_text("new lock\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, "", "failed")

    with pytest.raises(WorkspaceUpgradeError, match="validation failed"):
        WorkspaceUpgrader(tmp_path, runner=failing).apply("v0.6.0")

    assert not (tmp_path / "uv.lock").exists()
    assert not (tmp_path / "README.md").exists()
    assert pyproject.read_text(encoding="utf-8") == DEPENDENCY


def test_upgrade_does_not_rewrite_unmanaged_readme_on_success(tmp_path):
    (tmp_path / "pyproject.toml").write_text(DEPENDENCY, encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("# Author-owned documentation\n", encoding="utf-8")

    def passing(command):
        return subprocess.CompletedProcess(command, 0, "ok", "")

    report = WorkspaceUpgrader(tmp_path, runner=passing).apply("v0.6.0")

    assert report["readme_updated"] is False
    assert readme.read_text(encoding="utf-8") == "# Author-owned documentation\n"


def test_skill_diff_classifies_missing_changed_and_unchanged_files(tmp_path, monkeypatch):
    source = tmp_path / "skills"
    destination = tmp_path / ".agents" / "skills"
    source.mkdir()
    destination.mkdir(parents=True)
    (source / "missing.md").write_text("new", encoding="utf-8")
    (source / "changed.md").write_text("new", encoding="utf-8")
    (source / "same.md").write_text("same", encoding="utf-8")
    (destination / "changed.md").write_text("old", encoding="utf-8")
    (destination / "same.md").write_text("same", encoding="utf-8")
    monkeypatch.setattr("content_creator.upgrade.Path.with_name", lambda *_: tmp_path)

    changes = WorkspaceUpgrader(tmp_path)._skill_changes()

    assert changes == {
        "missing": [".agents/skills/missing.md"],
        "changed": [".agents/skills/changed.md"],
        "unchanged": [".agents/skills/same.md"],
    }


def test_upgrade_audit_treats_unreadable_historical_runs_as_blocking(project):
    state = project / "runs" / "corrupt-run" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("not-json", encoding="utf-8")

    findings = UpgradeCompatibilityAudit(project)._run_findings()

    assert findings[0]["run_status"] == "unreadable"
    assert findings[0]["outcome"] == "blocking"
    assert findings[0]["publication_blocked"] is True
    assert UpgradeCompatibilityAudit._run_status({"blocking": 1}) == "blocking"


def test_upgrade_audit_reports_an_uncreated_idempotency_index_as_compatible(tmp_path):
    finding = UpgradeCompatibilityAudit(tmp_path)._idempotency_finding()

    assert finding["outcome"] == "compatible"
    assert finding["detail"] == {"index": "not_created"}


def test_upgrade_audit_skips_unaffected_runs_and_does_not_duplicate_events(project):
    store = RunStore(project)
    detail = "core=v1.0.0->v1.1.0, pack=general-text"
    state = RunState(
        id="migration-run",
        status=RunStatus.READY,
        work_order=WorkOrder(request="Draft", topic="Draft"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
        events=[RunEvent(name="legacy_pack_options_resolved", detail=detail)],
    )
    store.create(state)
    UpgradeCompatibilityAudit(project)._persist_run_findings(
        [
            {"run_id": "ignored", "outcome": "compatible", "pack": "general-text"},
            {
                "run_id": state.id,
                "outcome": "automatically_migrated",
                "pack": "general-text",
            },
        ],
        "v1.0.0",
        "v1.1.0",
    )

    stored = store.load(state.id)
    assert [event.name for event in stored.events].count("legacy_pack_options_resolved") == 1
    assert (store.run_dir(state.id) / "pack-migration.json").exists()
