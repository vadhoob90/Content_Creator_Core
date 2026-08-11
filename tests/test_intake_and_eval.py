from types import SimpleNamespace

import pytest

import content_creator.evaluation as evaluation
from content_creator.cli import main
from content_creator.configuration import Configuration
from content_creator.domain import PlanningDecision, RunStatus, WorkOrder
from content_creator.evaluation import run_live_suite, run_replay_suite
from content_creator.intake import BriefingAgent, ClarificationRequired
from content_creator.packs import PackRegistry
from content_creator.prompting import PromptAssembler
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.runner import AgentRunner
from content_creator.work_order_resolution import resolve_workspace_defaults


def test_explicit_intake_does_not_need_model():
    order = BriefingAgent().plan("Write a LinkedIn article with deep research")
    assert order.format == "article"
    assert order.research_depth.value == "deep"
    assert order.research_source.value == "agent"


def test_no_research_is_respected():
    order = BriefingAgent().plan("Write a post without research")
    assert order.research_depth.value == "none"
    assert order.research_source.value == "none"


@pytest.mark.parametrize(
    "prompt",
    [
        "Write a post. No external research is required.",
        "Write a post; external research is not needed.",
        "Write a post without external research.",
        "Write a post and do not conduct external research.",
        "Write a post; research isn't necessary.",
    ],
)
def test_no_external_research_phrases_are_respected(prompt):
    order = BriefingAgent().plan(prompt)

    assert order.research_depth.value == "none"
    assert order.research_source.value == "none"


def test_workspace_defaults_resolve_only_implicit_voice_and_pack(project):
    order = resolve_workspace_defaults(
        WorkOrder(request="Write", topic="Topic"),
        {"default_voice": "author-general", "default_pack": "linkedin-post"},
        PackRegistry(project),
    )

    assert order.voice_id == "author-general"
    assert order.content_pack == "linkedin-post"
    assert order.format == "post"

    explicit = resolve_workspace_defaults(
        WorkOrder(
            request="Write",
            topic="Topic",
            voice_id="campaign-voice",
            content_pack="linkedin-article",
            format="article",
        ),
        {"default_voice": "author-general", "default_pack": "linkedin-post"},
        PackRegistry(project),
    )
    assert explicit.voice_id == "campaign-voice"
    assert explicit.content_pack == "linkedin-article"
    assert explicit.format == "article"


def test_replay_harness_runs_both_provider_contracts(project):
    report = run_replay_suite(project, ["anthropic", "openai"])
    assert report["total"] == 14
    assert report["passed"] == 14
    assert (project / ".eval-results" / "route-matrix.json").exists()


def test_bedrock_live_eval_uses_supplied_research_for_the_search_case(project, monkeypatch):
    orders = []

    class Store:
        def read_artifact(self, run_id, name):
            del run_id, name
            return "[]"

        def run_dir(self, run_id):
            directory = project / "runs" / run_id
            directory.mkdir(parents=True, exist_ok=True)
            return directory

    class OfflineOrchestrator:
        def __init__(self, root, max_revisions):
            del root, max_revisions
            self.store = Store()

        def start(self, order):
            orders.append(order)
            return SimpleNamespace(
                id="live-{}".format(len(orders)),
                status=RunStatus.READY,
                revision=0,
            )

    monkeypatch.setattr(evaluation, "Orchestrator", OfflineOrchestrator)

    report = run_live_suite(project, ["bedrock"])

    assert report["total"] == 2
    assert report["passed"] == 2
    researched = next(order for order in orders if order.research_depth.value == "deep")
    assert researched.research_source.value == "supplied"
    assert researched.supplied_research_path.endswith("bedrock-live-research.json")


def test_ambiguous_intake_can_request_clarification(project):
    decision = PlanningDecision(
        needs_clarification=True,
        clarification_questions=["Should this be a post or article?"],
    )
    fake = FakeProvider({"briefing-agent": [decision]})
    runner = AgentRunner(
        Configuration(project),
        ProviderRegistry({"anthropic": fake}),
        PromptAssembler(project),
    )
    planner = BriefingAgent(runner)
    try:
        planner.plan("Help me write something")
    except ClarificationRequired as exc:
        assert exc.questions == ["Should this be a post or article?"]
    else:
        raise AssertionError("Expected clarification")


def test_cli_plan_command_is_exercised(project, capsys):
    result = main(
        [
            "--root",
            str(project),
            "plan",
            "Write a post without research",
        ]
    )
    assert result == 0
    assert '"research_depth": "none"' in capsys.readouterr().out


def test_cli_eval_command_is_exercised(project):
    result = main(
        [
            "--root",
            str(project),
            "eval",
            "--providers",
            "anthropic",
        ]
    )
    assert result == 0
