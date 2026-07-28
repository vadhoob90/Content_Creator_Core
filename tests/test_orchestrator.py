import json

import pytest
from conftest import passing_critique, research_brief, valid_draft

from content_creator.domain import RunStatus, WorkOrder
from content_creator.orchestrator import OrchestrationError, Orchestrator
from content_creator.providers import FakeProvider, ProviderError, ProviderRegistry
from content_creator.storage import StorageError


def make_orchestrator(project, responses, max_revisions=3):
    return Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": FakeProvider(responses)}),
        max_revisions=max_revisions,
    )


@pytest.mark.parametrize(
    "format_,depth,source",
    [
        ("post", "none", "none"),
        ("post", "light", "agent"),
        ("post", "deep", "agent"),
        ("article", "none", "none"),
        ("article", "light", "agent"),
        ("article", "deep", "agent"),
    ],
)
def test_six_primary_routes(project, format_, depth, source):
    responses = {
        "writer": [valid_draft(format_ == "article", depth != "none")],
        "critic": [passing_critique()],
    }
    if source == "agent":
        responses["researcher"] = [research_brief()]
    orchestrator = make_orchestrator(project, responses)
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack=(
                "linkedin-article" if format_ == "article" else "linkedin-post"
            ),
            format=format_,
            research_depth=depth,
            research_source=source,
        )
    )
    if depth == "deep":
        assert state.status == RunStatus.AWAITING_RESEARCH_APPROVAL
        state = orchestrator.resume_research(state.id, True)
    assert state.status == RunStatus.READY
    assert (project / state.final_draft_path).exists()


def test_general_text_runs_end_to_end_and_snapshots_context(project):
    orchestrator = make_orchestrator(
        project,
        {"writer": [valid_draft()], "critic": [passing_critique()]},
    )
    state = orchestrator.start(
        WorkOrder(
            request="Explain a useful system",
            topic="A useful system",
            content_pack="general-text",
            format="text",
            pack_options={"length": "50:600"},
        )
    )
    context = json.loads(
        (project / "runs" / state.id / "resolved-context.json").read_text()
    )
    assert state.status == RunStatus.READY
    assert context["content_pack"] == {"id": "general-text", "version": "1.0.0"}
    assert context["voice"]["version"] == "placeholder"


@pytest.mark.parametrize(
    "format_,depth",
    [
        ("post", "light"),
        ("post", "deep"),
        ("article", "light"),
        ("article", "deep"),
    ],
)
def test_supplied_research_skips_researcher_and_checkpoint(project, format_, depth):
    brief_path = project / "brief.json"
    brief_path.write_text(json.dumps(research_brief()), encoding="utf-8")
    fake = FakeProvider(
        {
            "writer": [valid_draft(article=format_ == "article", researched=True)],
            "critic": [passing_critique()],
        }
    )
    orchestrator = Orchestrator(
        project, registry=ProviderRegistry({"anthropic": fake})
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack=(
                "linkedin-article" if format_ == "article" else "linkedin-post"
            ),
            format=format_,
            research_depth=depth,
            research_source="supplied",
            supplied_research_path="brief.json",
        )
    )
    assert state.status == RunStatus.READY
    assert not state.route_plan.requires_research_checkpoint
    assert all(request.role != "researcher" for request in fake.requests)


def test_research_rejection_stops_before_writer(project):
    fake = FakeProvider({"researcher": [research_brief()]})
    orchestrator = Orchestrator(
        project, registry=ProviderRegistry({"anthropic": fake})
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="linkedin-post",
            format="post",
            research_depth="deep",
            research_source="agent",
        )
    )
    state = orchestrator.resume_research(state.id, False, "Change the scope")
    assert state.status == RunStatus.NEEDS_AUTHOR
    assert all(request.role != "writer" for request in fake.requests)


def test_revision_limit_preserves_latest_draft(project):
    bad = passing_critique(7)
    orchestrator = make_orchestrator(
        project,
        {
            "writer": [valid_draft(), valid_draft()],
            "critic": [bad, bad],
        },
        max_revisions=2,
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="linkedin-post",
            format="post",
        )
    )
    assert state.status == RunStatus.NEEDS_AUTHOR
    assert state.revision == 2
    assert (project / state.final_draft_path).exists()


def test_failure_is_persisted(project):
    orchestrator = make_orchestrator(
        project, {"writer": [ProviderError("provider down")]}
    )
    with pytest.raises(ProviderError):
        orchestrator.start(
            WorkOrder(
                request="write",
                topic="topic",
                content_pack="linkedin-post",
                format="post",
            )
        )
    states = list((project / "runs").glob("*/state.json"))
    saved = json.loads(states[0].read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
    assert "provider down" in saved["last_error"]


def test_invalid_research_brief_fails_before_drafting(project):
    bad_brief = research_brief()
    bad_brief["evidence"][0]["source_urls"] = ["https://unknown.example/source"]
    fake = FakeProvider({"researcher": [bad_brief]})
    orchestrator = Orchestrator(
        project, registry=ProviderRegistry({"anthropic": fake})
    )
    with pytest.raises(OrchestrationError, match="unknown source"):
        orchestrator.start(
            WorkOrder(
                request="write",
                topic="topic",
                content_pack="linkedin-post",
                format="post",
                research_depth="light",
                research_source="agent",
            )
        )
    assert all(request.role != "writer" for request in fake.requests)


def test_publish_updates_learning_and_refuses_overwrite(project):
    extraction = {
        "candidates": [
            {
                "role": "writer",
                "principle": "Prefer a concrete opening.",
                "evidence": "The author explicitly requested it.",
                "status": "active",
                "confidence": 0.9,
            }
        ],
        "author_signal": "explicit",
    }
    orchestrator = make_orchestrator(
        project,
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
            "learning-extractor": [extraction],
        },
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="Unique topic",
            content_pack="linkedin-post",
            format="post",
        )
    )
    state = orchestrator.publish(
        state.id, filename="published-test.md", feedback="Use concrete openings"
    )
    assert state.status == RunStatus.PUBLISHED
    memory = json.loads(
        (
            project / "profiles" / "default" / "learnings" / "memory.json"
        ).read_text(encoding="utf-8")
    )
    assert memory["records"][0]["status"] == "active"
    with pytest.raises(OrchestrationError):
        orchestrator.publish(state.id, filename="published-test.md")


def test_publish_without_explicit_feedback_keeps_inference_provisional(project):
    extraction = {
        "candidates": [
            {
                "role": "writer",
                "principle": "Use short openings.",
                "evidence": "Inferred from publication.",
                "status": "provisional",
                "confidence": 0.6,
            }
        ]
    }
    orchestrator = make_orchestrator(
        project,
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
            "learning-extractor": [extraction],
        },
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="linkedin-post",
            format="post",
        )
    )
    orchestrator.publish(state.id, filename="x.md")
    memory = json.loads(
        (
            project / "profiles" / "default" / "learnings" / "memory.json"
        ).read_text(encoding="utf-8")
    )
    assert memory["records"][0]["status"] == "provisional"


def test_publish_never_overwrites_existing_file(project):
    target = (
        project / "content" / "linkedin-post" / "published" / "existing.md"
    )
    target.write_text("existing", encoding="utf-8")
    orchestrator = make_orchestrator(
        project, {"writer": [valid_draft()], "critic": [passing_critique()]}
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="linkedin-post",
            format="post",
        )
    )
    with pytest.raises(StorageError):
        orchestrator.publish(state.id, filename="existing.md")
    assert target.read_text(encoding="utf-8") == "existing"


def test_learning_failure_does_not_lose_approved_publication(project):
    orchestrator = make_orchestrator(
        project,
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
            "learning-extractor": [ProviderError("learning unavailable")],
        },
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="linkedin-post",
            format="post",
        )
    )
    state = orchestrator.publish(state.id, filename="safe.md")
    assert state.status == RunStatus.PUBLISHED
    assert (
        project / "content" / "linkedin-post" / "published" / "safe.md"
    ).exists()
    assert any(event.name == "learning_update_failed" for event in state.events)
