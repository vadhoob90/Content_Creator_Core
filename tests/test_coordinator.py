import json
import logging

import yaml

from content_creator.cli import main
from content_creator.coordinator import ContentCoordinator
from content_creator.domain import (
    RoutePlan,
    RunState,
    RunStatus,
    WorkOrder,
)
from content_creator.storage import RunStore


def test_coordinator_capabilities_expose_approval_boundaries(project, capsys):
    assert main(["--root", str(project), "coordinator", "capabilities"]) == 0
    result = json.loads(capsys.readouterr().out)

    operations = {item["id"]: item for item in result["operations"]}
    assert operations["workspace.inspect"]["mutates_workspace"] is False
    assert operations["run.submission-status"]["mutates_workspace"] is False
    assert operations["research.approve"]["requires_explicit_approval"] is True
    assert operations["content.publish-local"]["requires_explicit_approval"] is True
    assert operations["workspace.upgrade-preview"]["mutates_workspace"] is False
    assert operations["workspace.upgrade-apply"]["requires_explicit_approval"] is True
    assert result["boundaries"]["external_publication"] is False


def test_coordinator_context_uses_workspace_defaults_as_suggestions(project, capsys):
    configuration = {
        "coordinator": {
            "name": "Example Coordinator",
            "default_voice": "default",
            "default_pack": "linkedin-post",
            "external_publication": "disabled",
        }
    }
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump(configuration, sort_keys=False),
        encoding="utf-8",
    )

    assert main(["--root", str(project), "coordinator", "context"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["coordinator"]["name"] == "Example Coordinator"
    assert result["suggested_voice_id"] == "default"
    assert result["coordinator"]["default_pack"] == "linkedin-post"
    assert result["provider"] == "anthropic"
    assert result["provider_status"]["name"] == "anthropic"
    assert result["warnings"] == []
    assert result["latest_upgrade_compatibility"] is None


def test_coordinator_context_surfaces_latest_upgrade_audit(project):
    directory = project / ".content-creator" / "upgrades"
    directory.mkdir(parents=True)
    report = {
        "workspace_readiness": "compatible",
        "historical_run_compatibility": "decision_required",
        "chat_summary": ["One historical run needs a decision"],
        "decision_prompts": [{"run_id": "legacy-run"}],
    }
    (directory / "v1-to-v2.json").write_text(json.dumps(report), encoding="utf-8")

    context = ContentCoordinator(project).context()

    assert context["latest_upgrade_compatibility"] == report


def test_coordinator_reports_bedrock_credential_chain_status(project, monkeypatch):
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump({"provider": {"default": "bedrock"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AWS_PROFILE", "content-author")

    status = ContentCoordinator(project)._provider_status()

    assert status.name == "bedrock"
    assert status.status == "configured"
    assert status.detail == "AWS credential chain"


def test_coordinator_next_actions_come_from_persisted_state(project):
    store = RunStore(project)
    state = RunState(
        id="approval-run",
        status=RunStatus.AWAITING_RESEARCH_APPROVAL,
        work_order=WorkOrder(
            request="Explain a legal development",
            topic="Legal development",
        ),
        route_plan=RoutePlan(
            route="text-deep-agent",
            stages=["researcher", "writer"],
            requires_research_checkpoint=True,
        ),
    )
    store.create(state)
    store.write_artifact(state.id, "research.json", {"summary": "Evidence"})

    result = ContentCoordinator(project).next_actions(state.id)
    actions = {item["id"]: item for item in result["actions"]}

    assert result["requires_human_input"] is True
    assert actions["approve-research"]["command"] == [
        "approve-research",
        "approval-run",
    ]
    assert actions["approve-research"]["requires_confirmation"] is True
    assert "runs/approval-run/research.json" in result["artifacts"]


def test_coordinator_lists_recent_runs(project):
    store = RunStore(project)
    store.create(
        RunState(
            id="recent-run",
            status=RunStatus.READY,
            work_order=WorkOrder(request="Draft", topic="Draft"),
            route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
        )
    )

    result = ContentCoordinator(project).runs()

    assert result["runs"][0]["run_id"] == "recent-run"
    assert result["runs"][0]["requires_human_input"] is True


def test_coordinator_warns_when_a_persisted_run_is_unreadable(project, caplog):
    state_path = project / "runs" / "broken-run" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("not-json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = ContentCoordinator(project).runs()

    assert result["runs"] == []
    assert "Skipping unreadable run state at runs/broken-run/state.json" in caplog.text


def test_coordinator_replaces_publish_action_with_diagnostic_choices(project):
    store = RunStore(project)
    state = RunState(
        id="diagnostic-run",
        status=RunStatus.READY,
        work_order=WorkOrder(request="Draft", topic="Draft"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
        final_draft_path="runs/diagnostic-run/final.md",
        support_candidate_path=("runs/diagnostic-run/support-candidate.json"),
        pending_support_count=1,
    )
    store.create(state)
    store.write_artifact(state.id, "final.md", "Draft")
    store.write_artifact(state.id, "support-candidate.json", [])

    result = ContentCoordinator(project).next_actions(state.id)
    actions = {item["id"]: item for item in result["actions"]}

    assert result["diagnostic_attention_required"] is True
    assert "publish-local" not in actions
    assert actions["publish-only"]["command"][-1] == "publish-only"
    assert actions["publish-and-prepare-issue"]["command"][-1] == "prepare-issue"
