import hashlib
import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.domain import RunStatus, WorkOrder
from content_creator.orchestrator import OrchestrationError, Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.voices import hash_file


def _activate_voice(project):
    profile = project / "profiles" / "verified-author"
    version = profile / "versions" / "1.0.0"
    (profile / "learnings").mkdir(parents=True)
    version.mkdir(parents=True)
    profile_path = version / "profile.md"
    profile_path.write_text(
        "# Verified author voice\n\nUse concrete explanations.\n", encoding="utf-8"
    )
    (version / "source-index.json").write_text("[]", encoding="utf-8")
    (version / "manifest.json").write_text(
        json.dumps(
            {
                "id": "verified-author",
                "display_name": "Verified Author",
                "version": "1.0.0",
                "status": "active",
                "candidate_hash": "sha256:fixture",
                "components": {"profile": "profile.md"},
                "component_hashes": {"profile": hash_file(profile_path)},
                "supported_packs": {"linkedin-post": "high"},
                "authorisation": {"confirmed": True},
            }
        ),
        encoding="utf-8",
    )
    (project / "profiles" / "registry.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "profiles": {
                    "verified-author": {
                        "status": "active",
                        "active_version": "1.0.0",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (profile / "learnings" / "memory.json").write_text(
        json.dumps({"version": 1, "records": []}), encoding="utf-8"
    )


def _learning(principle):
    return {
        "candidates": [
            {
                "role": "writer",
                "principle": principle,
                "evidence": "Explicit author feedback",
                "status": "active",
                "confidence": 1,
                "source_event": "author_feedback",
            }
        ],
        "author_signal": "explicit_feedback",
    }


def _reviewed_run(project, learning_responses):
    _activate_voice(project)
    fake = FakeProvider(
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
            "learning-extractor": learning_responses,
        }
    )
    orchestrator = Orchestrator(project, registry=ProviderRegistry({"anthropic": fake}))
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="Learning-only feedback",
            content_pack="linkedin-post",
            voice_id="verified-author",
            format="post",
        )
    )
    return orchestrator, fake, state


def test_reviewed_run_accepts_idempotent_learning_without_publication(project):
    orchestrator, fake, state = _reviewed_run(
        project, [_learning("Open with the concrete operational constraint.")]
    )

    learned = orchestrator.learn(
        state.id,
        "Open with the concrete operational constraint.",
        idempotency_key="post-review-feedback-1",
    )
    repeated = orchestrator.learn(
        state.id,
        "Open with the concrete operational constraint.",
        idempotency_key="post-review-feedback-1",
    )

    run = project / "runs" / state.id
    memory = json.loads(
        (project / "profiles" / "verified-author" / "learnings" / "memory.json").read_text()
    )
    request_name = "learning-request-{}.json".format(
        hashlib.sha256(b"post-review-feedback-1").hexdigest()[:16]
    )
    request = json.loads((run / request_name).read_text())
    assert learned.status == RunStatus.READY
    assert repeated.status == RunStatus.READY
    assert learned.published_path is None
    assert list((project / "content" / "linkedin-post" / "published").glob("*.md")) == []
    assert len(memory["records"]) == 1
    assert memory["records"][0]["status"] == "active"
    assert memory["records"][0]["voice_id"] == "verified-author"
    assert memory["records"][0]["voice_version"] == "1.0.0"
    assert memory["records"][0]["content_pack"] == "linkedin-post"
    assert request["status"] == "complete"
    assert request["resolved_context"]["voice_version"] == "1.0.0"
    assert (run / "learning-assessment-01.json").exists()
    assert (run / "learning-extraction-01.json").exists()
    extraction = json.loads((run / "learning-extraction-01.json").read_text())
    assert extraction["schema_version"] == "1.0"
    assert len([item for item in fake.requests if item.role == "learning-extractor"]) == 1
    assert any(item.name == "learning_update_completed" for item in learned.events)


def test_published_run_can_learn_without_rewriting_or_duplicating_publication(project):
    orchestrator, _, state = _reviewed_run(
        project,
        [
            _learning("Retain a restrained conclusion."),
            _learning("Name the operational consequence before the abstraction."),
        ],
    )
    published = orchestrator.publish(state.id, filename="learning-source.md")
    target = project / str(published.published_path)
    original = target.read_text(encoding="utf-8")

    learned = orchestrator.learn(
        state.id,
        "Name the operational consequence before the abstraction.",
        idempotency_key="post-publication-feedback-1",
    )

    memory = json.loads(
        (project / "profiles" / "verified-author" / "learnings" / "memory.json").read_text()
    )
    assert learned.status == RunStatus.PUBLISHED
    assert target.read_text(encoding="utf-8") == original
    assert [path.name for path in target.parent.glob("*.md")] == ["learning-source.md"]
    assert len(memory["records"]) == 2


def test_learning_idempotency_key_rejects_different_feedback(project):
    orchestrator, _, state = _reviewed_run(project, [_learning("Use concrete openings.")])
    orchestrator.learn(state.id, "Use concrete openings.", idempotency_key="feedback-1")

    with pytest.raises(OrchestrationError, match="different feedback"):
        orchestrator.learn(state.id, "Use a different ending.", idempotency_key="feedback-1")


@pytest.mark.parametrize("invalid_context", ["missing", "inactive", "unverifiable"])
def test_learning_fails_clearly_for_invalid_persisted_voice(project, invalid_context):
    orchestrator, _, state = _reviewed_run(project, [])
    registry_path = project / "profiles" / "registry.json"
    registry = json.loads(registry_path.read_text())
    if invalid_context == "missing":
        registry["profiles"].pop("verified-author")
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        message = "Unknown voice"
    elif invalid_context == "inactive":
        registry["profiles"]["verified-author"]["status"] = "inactive"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        message = "not active"
    else:
        profile = project / "profiles" / "verified-author" / "versions" / "1.0.0" / "profile.md"
        profile.write_text("tampered", encoding="utf-8")
        message = "hash mismatch"

    with pytest.raises(OrchestrationError, match=message):
        orchestrator.learn(state.id, "Keep this durable rule.", idempotency_key="feedback-1")

    persisted = orchestrator.store.load(state.id)
    assert persisted.status == RunStatus.READY
    assert any(item.name == "learning_update_failed" for item in persisted.events)
