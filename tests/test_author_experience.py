import json

import yaml

import content_creator.cli as cli
from content_creator.cli import main
from content_creator.domain import RoutePlan, RunState, RunStatus, WorkOrder
from content_creator.storage import RunStore


def test_overview_has_human_and_machine_readable_views(project, capsys):
    assert main(["--root", str(project), "overview"]) == 0
    text = capsys.readouterr().out
    assert "Content Creator workspace" in text
    assert "Active voice:" in text
    assert "Recommended next action:" in text

    assert main(["--root", str(project), "overview", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "1.1"
    assert result["recommended_action"]["id"] == "select-provider"
    assert result["provider"] == "anthropic"
    assert result["provider_status"]["name"] == "anthropic"


def test_start_uses_persisted_run_state_before_new_work(project, capsys):
    store = RunStore(project)
    store.create(
        RunState(
            id="research-run",
            status=RunStatus.AWAITING_RESEARCH_APPROVAL,
            work_order=WorkOrder(request="Research", topic="Research"),
            route_plan=RoutePlan(
                route="text-deep-agent",
                stages=["researcher"],
                requires_research_checkpoint=True,
            ),
        )
    )

    assert main(["--root", str(project), "start"]) == 0
    output = capsys.readouterr().out
    assert "research checkpoint" in output
    assert "coordinator next-actions research-run" in output


def test_start_json_exposes_typed_recommendation(project, capsys):
    assert main(["--root", str(project), "start", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["recommended_action"]["mutates_workspace"] is True
    assert result["recommended_action"]["requires_confirmation"] is True
    assert result["health"]["status"] == "ok"


def test_start_outside_workspace_recommends_creation(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "start", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["is_workspace"] is False
    assert result["recommended_action"]["id"] == "create-workspace"
    assert result["recommended_action"]["mutates_workspace"] is True


def test_start_request_proposes_work_without_mutating(project, capsys, monkeypatch):
    class FakeOrchestrator:
        def __init__(self, root):
            self.root = root

        def plan_request(self, request, provider=None):
            return WorkOrder(
                request=request,
                topic="A useful system",
                content_pack="linkedin-post",
                format="post",
                provider=provider,
            )

    monkeypatch.setattr(cli, "Orchestrator", FakeOrchestrator)

    assert (
        main(
            [
                "--root",
                str(project),
                "start",
                "Write a useful post",
                "--provider",
                "anthropic",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["mutates_workspace"] is False
    assert result["work_order"]["content_pack"] == "linkedin-post"
    assert result["approval_points"][-1] == "repository-local publication"


def test_start_and_run_share_workspace_voice_and_no_research_resolution(
    project, capsys, monkeypatch
):
    configuration_path = project / "content-creator.yaml"
    configuration = {
        "coordinator": {
            "default_voice": "test-general",
            "default_pack": "general-text",
        }
    }
    configuration_path.write_text(
        yaml.safe_dump(configuration, sort_keys=False),
        encoding="utf-8",
    )

    request = (
        "Write a short LinkedIn post explaining why calculus matters. "
        "No external research is required."
    )
    assert main(["--root", str(project), "start", request, "--json"]) == 0
    proposed = json.loads(capsys.readouterr().out)["work_order"]

    class FakeOrchestrator:
        def __init__(self, root):
            from content_creator.orchestrator import Orchestrator

            self.delegate = Orchestrator(root)
            self.runner = self.delegate.runner

        def plan_request(self, request, provider=None):
            return self.delegate.plan_request(request, provider)

        def start(self, order):
            return order

    monkeypatch.setattr(cli, "Orchestrator", FakeOrchestrator)
    assert main(["--root", str(project), "run", request]) == 0
    executed = json.loads(capsys.readouterr().out)

    for order in (proposed, executed):
        assert order["voice_id"] == "test-general"
        assert order["research_depth"] == "none"
        assert order["research_source"] == "none"
