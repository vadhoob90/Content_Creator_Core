import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.domain import (
    PerspectiveSelection,
    RoutePlan,
    RunState,
    WorkOrder,
)
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.storage import RunStore


def _orchestrator(project):
    return Orchestrator(
        project,
        registry=ProviderRegistry(
            {
                "anthropic": FakeProvider(
                    {
                        "writer": [valid_draft()],
                        "critic": [passing_critique(), passing_critique()],
                        "learning-extractor": [{"candidates": []}],
                    }
                )
            }
        ),
    )


def test_review_copy_has_generated_table_while_final_draft_stays_clean(project):
    state = _orchestrator(project).start(
        WorkOrder(
            request="Explain a useful system.",
            topic="Useful system",
            pack_options={"length": "50:600"},
        )
    )
    run = project / "runs" / state.id
    manifest = json.loads((run / "production-manifest.json").read_text(encoding="utf-8"))
    review = (run / "review.md").read_text(encoding="utf-8")
    final = (run / "final.md").read_text(encoding="utf-8")

    assert state.production_manifest_path == f"runs/{state.id}/production-manifest.json"
    assert state.review_draft_path == f"runs/{state.id}/review.md"
    assert manifest["content_pack"]["id"] == "general-text"
    assert manifest["content_pack"]["version"] == "1.0.0"
    assert manifest["voice"] == {"id": "default", "version": "placeholder"}
    assert manifest["perspectives"] == []
    assert manifest["status"] == "ready"
    assert {item["role"] for item in manifest["invocations"]} == {"writer", "critic"}
    assert "## Production details" in review
    assert "| Content pack | general-text v1.0.0 |" in review
    assert final.strip() in review
    assert "Production details" not in final


@pytest.mark.parametrize("perspective_count", [0, 1, 2])
def test_manifest_renders_zero_one_or_multiple_perspectives(project, perspective_count):
    selections = [
        PerspectiveSelection(
            context_id=f"context-{index}",
            version=f"{index}.0.0",
            reason="test selection",
            confidence=0.9,
        )
        for index in range(1, perspective_count + 1)
    ]
    state = RunState(
        work_order=WorkOrder(
            request="write",
            topic="topic",
            voice_version="1.0.0",
            resolved_voice=True,
            perspective_selections=selections,
        ),
        route_plan=RoutePlan(route="test", stages=[]),
    )
    RunStore(project).create(state)
    run = project / "runs" / state.id
    manifest = json.loads((run / "production-manifest.json").read_text(encoding="utf-8"))
    summary = (run / "production-manifest.md").read_text(encoding="utf-8")

    assert len(manifest["perspectives"]) == perspective_count
    if perspective_count:
        assert "context-1 v1.0.0" in summary
    else:
        assert "| Perspectives | None |" in summary
    if perspective_count == 2:
        assert "context-2 v2.0.0" in summary


def test_revision_and_publication_refresh_manifest_without_decorating_publication(project):
    orchestrator = _orchestrator(project)
    state = orchestrator.start(
        WorkOrder(
            request="Explain a useful system.",
            topic="Useful system",
            pack_options={"length": "50:600"},
        )
    )
    edited = valid_draft().replace("useful writing system", "reviewed writing system", 1)
    revised = orchestrator.revise(
        state.id,
        feedback="Use the reviewed wording.",
        draft=edited,
        idempotency_key="production-manifest-revision",
    )
    published = orchestrator.publish(revised.id, filename="manifest-test.md")
    run = project / "runs" / state.id
    manifest = json.loads((run / "production-manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (
            project
            / "publication-receipts/content/general-text/published/manifest-test.md.receipt.json"
        ).read_text(encoding="utf-8")
    )
    publication = project / str(published.published_path)

    assert manifest["status"] == "published"
    assert manifest["revision"] == 2
    assert manifest["publication"]["path"] == str(published.published_path)
    assert [item["role"] for item in manifest["invocations"]] == [
        "writer",
        "critic",
        "critic",
        "learning-extractor",
    ]
    assert receipt["content_pack_id"] == "general-text"
    assert receipt["content_pack_version"] == "1.0.0"
    assert "Production details" not in publication.read_text(encoding="utf-8")
    assert "reviewed writing system" in publication.read_text(encoding="utf-8")


def test_legacy_run_is_backfilled_on_next_state_save(project):
    store = RunStore(project)
    state = RunState(
        work_order=WorkOrder(request="write", topic="legacy"),
        route_plan=RoutePlan(route="legacy", stages=[]),
    )
    run = store.run_dir(state.id)
    run.mkdir(parents=True)
    (run / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")

    loaded = store.load(state.id)
    assert not (run / "production-manifest.json").exists()

    store.save_state(loaded)

    assert (run / "production-manifest.json").is_file()
    assert store.load(state.id).production_manifest_path == (
        f"runs/{state.id}/production-manifest.json"
    )
