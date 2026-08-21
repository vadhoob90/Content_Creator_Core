import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.coordinator import ContentCoordinator
from content_creator.domain import WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.publication_provenance import (
    PublicationProvenance,
    PublicationProvenanceError,
)
from content_creator.visual_contracts import VisualCritique
from content_creator.visual_preferences import VisualPreferenceMemory
from content_creator.visual_requests import VisualRenderRequest, VisualRequestWorkflow


def _orchestrator(project, learning=None):
    provider = FakeProvider(
        {
            "writer": [valid_draft(), valid_draft()],
            "critic": [passing_critique(), passing_critique()],
            "learning-extractor": learning or [{"candidates": []}, {"candidates": []}],
        }
    )
    return Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": provider}),
    )


def _approved_visual(orchestrator, state, *, parent_asset_id=None):
    pack = orchestrator.packs.resolve(
        state.work_order.content_pack,
        state.work_order.pack_options,
    )
    result = VisualRequestWorkflow(
        orchestrator.root,
        workflow=orchestrator.visuals,
    ).render(
        profile=pack.visuals,
        request=VisualRenderRequest(
            run_id=state.id,
            pack_id=pack.id,
            pack_version=pack.version,
            request="Create an image for this post.",
            parent_asset_id=parent_asset_id,
        ),
    )
    asset = result.assets[0]
    orchestrator.visuals.record_critique(
        state.id,
        asset.asset_id,
        VisualCritique(summary="Approved", strengths=["Clear at feed size"]),
    )
    orchestrator.visuals.select(state.id, asset.asset_id)
    return orchestrator.visuals.approve(state.id, asset.asset_id)


def _start_linkedin(orchestrator, *, parent=None):
    return orchestrator.start(
        WorkOrder(
            request="Write a LinkedIn post.",
            topic="Publication packages",
            content_pack="linkedin-post",
            format="post",
            parent_run_id=parent.id if parent else None,
            content_session_id=(
                parent.work_order.content_session_id if parent else "publication-session"
            ),
        )
    )


def test_publication_receipt_records_text_and_approved_visual(project):
    orchestrator = _orchestrator(project)
    state = _start_linkedin(orchestrator)
    approved = _approved_visual(orchestrator, state)

    published = orchestrator.publish(state.id, filename="package.md")
    receipt_path = project / (
        "publication-receipts/content/linkedin-post/published/package.md.receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert published.published_visual_path
    assert len(published.published_media) == 1
    media = published.published_media[0]
    assert media.asset_id == approved.asset_id
    assert media.alt_text == approved.alt_text
    assert media.mime_type == "image/svg+xml"
    assert media.width == approved.width
    assert media.height == approved.height
    assert media.sha256.startswith("sha256:")
    assert {item["role"] for item in receipt["artifacts"]} == {"content", "portrait-feed"}
    visual = next(item for item in receipt["artifacts"] if item["role"] == "portrait-feed")
    assert visual["path"] == published.published_visual_path
    assert visual["alt_text"] == approved.alt_text
    assert visual["asset_id"] == approved.asset_id
    decision = json.loads((project / "runs" / state.id / "visuals" / "decision.json").read_text())
    assert decision["decision"] == "approved"


def test_publication_rolls_back_text_and_visual_when_receipt_fails(project, monkeypatch):
    orchestrator = _orchestrator(project)
    state = _start_linkedin(orchestrator)
    _approved_visual(orchestrator, state)

    def fail_issue(*args, **kwargs):  # noqa: ARG001
        raise PublicationProvenanceError("receipt unavailable")

    monkeypatch.setattr(orchestrator.publications, "issue", fail_issue)
    with pytest.raises(PublicationProvenanceError, match="receipt unavailable"):
        orchestrator.publish(state.id, filename="rollback.md")

    assert not (project / "content/linkedin-post/published/rollback.md").exists()
    assert list((project / "content/linkedin-post/visuals").glob(f"{state.id}-*")) == []
    persisted = orchestrator.store.load(state.id)
    assert persisted.published_path is None
    assert persisted.published_visual_path is None


def test_visual_replacement_updates_receipt_and_preserves_history(project):
    orchestrator = _orchestrator(project)
    state = _start_linkedin(orchestrator)
    first = _approved_visual(orchestrator, state)
    published = orchestrator.publish(state.id, filename="replace.md")
    text_path = project / str(published.published_path)
    original_text = text_path.read_text(encoding="utf-8")
    original_visual_path = published.published_visual_path

    replacement = _approved_visual(orchestrator, published, parent_asset_id=first.asset_id)
    replaced = orchestrator.replace_visual(state.id, replacement.asset_id)

    assert replaced.published_path == published.published_path
    assert text_path.read_text(encoding="utf-8") == original_text
    assert replaced.published_visual_path != original_visual_path
    assert (project / str(original_visual_path)).exists()
    receipt_path = project / (
        "publication-receipts/content/linkedin-post/published/replace.md.receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["revision"] == 2
    assert receipt["supersedes_receipt_hash"].startswith("sha256:")
    history = list(receipt_path.parent.glob("replace.md.receipt.r1-*.json"))
    assert len(history) == 1
    assert len(list(text_path.parent.glob("replace*.md"))) == 1


def test_failed_publication_learning_is_durable_visible_and_retryable(project):
    orchestrator = _orchestrator(
        project,
        learning=[RuntimeError("native state unavailable"), {"candidates": []}],
    )
    state = _start_linkedin(orchestrator)
    published = orchestrator.publish(state.id, filename="learning-pending.md")

    request_path = project / "runs" / state.id / "publication-learning-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert published.status.value == "published"
    assert published.pending_learning_count == 1
    assert request["status"] == "pending"
    actions = ContentCoordinator(project).next_actions(state.id)["actions"]
    assert "retry-learning" in {item["id"] for item in actions}

    retried = orchestrator.retry_pending_learning(state.id)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert retried.pending_learning_count == 0
    assert request["status"] == "complete"


def test_coordinator_marks_ready_ancestor_as_superseded_by_published_child(project):
    orchestrator = _orchestrator(project)
    parent = _start_linkedin(orchestrator)
    child = _start_linkedin(orchestrator, parent=parent)
    orchestrator.publish(child.id, filename="authoritative.md")

    runs = ContentCoordinator(project).runs()["runs"]
    indexed = {item["run_id"]: item for item in runs}

    assert indexed[child.id]["authoritative"] is True
    assert indexed[parent.id]["authoritative"] is False
    assert indexed[parent.id]["superseded_by_run_id"] == child.id
    assert ContentCoordinator(project).snapshot().recommended_action.id != "review-draft"


def test_verification_can_be_scoped_to_run_or_artifact(project):
    orchestrator = _orchestrator(project)
    state = _start_linkedin(orchestrator)
    published = orchestrator.publish(state.id, filename="scoped.md")
    legacy = project / "content/linkedin-post/published/legacy.md"
    legacy.write_text("legacy", encoding="utf-8")
    service = PublicationProvenance(
        project,
        {"policy": "required", "receipts_directory": "publication-receipts"},
    )

    assert service.verify()["status"] == "failed"
    assert service.verify(run_id=state.id)["status"] == "ok"
    assert service.verify(artifact_path=published.published_path)["status"] == "ok"
    assert (
        service.verify(artifact_path="content/linkedin-post/published/missing.md")["status"]
        == "failed"
    )
    with pytest.raises(PublicationProvenanceError, match="Unknown run"):
        service.verify(run_id="unknown")


def test_visual_preferences_and_locked_assets_are_separate_and_injected(project):
    orchestrator = _orchestrator(project)
    state = _start_linkedin(orchestrator)
    logo = project / "brand-logo.svg"
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h10v10z"/></svg>')
    (project / "visual-brand.json").write_text(
        json.dumps(
            {
                "accent": "#ABCDEF",
                "locked_assets": [{"id": "brand-logo", "path": "brand-logo.svg", "role": "logo"}],
            }
        ),
        encoding="utf-8",
    )
    memory = VisualPreferenceMemory(project, state.work_order.voice_id)
    memory.record(state.id, "Prefer tactile paper-cut editorial styling.")

    pack = orchestrator.packs.resolve("linkedin-post")
    result = VisualRequestWorkflow(project, workflow=orchestrator.visuals).render(
        profile=pack.visuals,
        request=VisualRenderRequest(
            run_id=state.id,
            pack_id=pack.id,
            pack_version=pack.version,
            request="Create an image for this post.",
        ),
    )

    assert "Prefer tactile paper-cut editorial styling." in result.brief.visual_preferences
    assert result.brief.locked_assets[0].id == "brand-logo"
    assert result.brief.locked_assets[0].sha256.startswith("sha256:")
    rendered = project / "runs" / state.id / result.assets[0].relative_path
    assert 'data-locked-asset="brand-logo"' in rendered.read_text(encoding="utf-8")
    assert "tactile paper-cut" not in (
        project / "profiles/default/learnings/memory.json"
    ).read_text(encoding="utf-8")
