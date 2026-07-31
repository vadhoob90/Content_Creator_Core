import json

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
    assert operations["research.approve"]["requires_explicit_approval"] is True
    assert operations["content.publish-local"]["requires_explicit_approval"] is True
    assert result["boundaries"]["external_publication"] is False


def test_coordinator_context_uses_workspace_defaults_as_suggestions(
    project, capsys
):
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


def test_coordinator_replaces_publish_action_with_diagnostic_choices(project):
    store = RunStore(project)
    state = RunState(
        id="diagnostic-run",
        status=RunStatus.READY,
        work_order=WorkOrder(request="Draft", topic="Draft"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
        final_draft_path="runs/diagnostic-run/final.md",
        support_candidate_path=(
            "runs/diagnostic-run/support-candidate.json"
        ),
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
    assert (
        actions["publish-and-prepare-issue"]["command"][-1]
        == "prepare-issue"
    )
