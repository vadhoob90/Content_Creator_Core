"""Exercise privacy, migration, and disposition failure boundaries."""

import json

import pytest
from pydantic import ValidationError

from content_creator.storage import RunStore
from content_creator.voice_evolution_models import EvolutionResult
from content_creator.voice_upgrade.eligibility import (
    _local_evidence_hashes,
    inspect_upgrade_eligibility,
)
from content_creator.voice_upgrade.epochs import prepare_epoch_transition
from content_creator.voice_upgrade.guidance import (
    apply_learning_overlays,
    write_learning_change_set,
)
from content_creator.voice_upgrade.models import (
    LearningClassification,
    LearningDisposition,
    LearningDispositionAction,
    LearningSelection,
)


def _disposition(
    learning_id: str,
    classification: LearningClassification,
    action: LearningDispositionAction,
    target: str | None = None,
) -> LearningDisposition:
    return LearningDisposition(
        learning_id=learning_id,
        classification=classification,
        disposition=action,
        rationale="Explicit author review.",
        target_guidance_id=target,
    )


def _selection(*dispositions: LearningDisposition) -> LearningSelection:
    return LearningSelection(
        voice_id="author",
        baseline_version="1.0.0",
        learning_epoch_hash="sha256:epoch",
        reviewed_by="Author",
        reviewed_at="2026-08-23T00:00:00+00:00",
        dispositions=list(dispositions),
    )


def test_learning_dispositions_reject_cross_boundary_routes():
    with pytest.raises(ValidationError, match="linguistic voice"):
        _disposition(
            "research",
            LearningClassification.RESEARCH_ONLY,
            LearningDispositionAction.INCORPORATE,
        )
    with pytest.raises(ValidationError, match="visual disposition"):
        _disposition(
            "visual",
            LearningClassification.VISUAL_PREFERENCE,
            LearningDispositionAction.CARRY_FORWARD,
        )
    with pytest.raises(ValidationError, match="perspective disposition"):
        _disposition(
            "perspective",
            LearningClassification.PERSPECTIVE,
            LearningDispositionAction.CARRY_FORWARD,
        )
    visual = _disposition(
        "visual",
        LearningClassification.VISUAL_PREFERENCE,
        LearningDispositionAction.ROUTE_VISUAL,
    )
    perspective = _disposition(
        "perspective",
        LearningClassification.PERSPECTIVE,
        LearningDispositionAction.ROUTE_PERSPECTIVE,
    )
    assert visual.disposition == LearningDispositionAction.ROUTE_VISUAL
    assert perspective.disposition == LearningDispositionAction.ROUTE_PERSPECTIVE


def test_learning_guidance_merges_explicit_changes_and_structured_overlays(tmp_path):
    explicit = tmp_path / "explicit.json"
    explicit.write_text(
        json.dumps(
            {
                "changes": [
                    {
                        "action": "remove",
                        "target_id": "obsolete",
                        "evidence_source_ids": ["source:review"],
                        "confidence": 1,
                        "rationale": "Author removed it.",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    profile = _disposition(
        "profile",
        LearningClassification.VOICE_PROFILE,
        LearningDispositionAction.INCORPORATE,
        "existing-pattern",
    )
    critic = _disposition(
        "critic",
        LearningClassification.CRITIC_RUBRIC,
        LearningDispositionAction.INCORPORATE,
    )
    retained = _disposition(
        "retained",
        LearningClassification.REMAIN_LEARNING,
        LearningDispositionAction.CARRY_FORWARD,
    )
    selection = _selection(profile, critic, retained)
    records = [
        {"id": "profile", "role": "writer", "principle": "Prefer concrete transitions."},
        {"id": "critic", "role": "critic", "principle": "Reject generic conclusions."},
        {"id": "retained", "role": "writer", "principle": "Keep this as learning."},
    ]
    output = write_learning_change_set(
        tmp_path / "combined.json",
        selection,
        records,
        explicit,
    )
    changes = json.loads(output.read_text(encoding="utf-8"))["changes"]
    assert [change["action"] for change in changes] == ["remove", "modify", "add"]
    assert changes[1]["replacement"]["category"] == "reviewed-learning-profile"
    assert changes[2]["replacement"]["category"] == "reviewed-learning-rubric"

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    evolved = EvolutionResult("profile", {}, {}, [])
    result = apply_learning_overlays(candidate, evolved, selection, records)
    assert result.constraints == {}
    assert result.rubric["reviewed_author_rules"]["critic"] == "Reject generic conclusions."


def test_learning_guidance_rejects_missing_and_researcher_evidence(tmp_path):
    incorporated = _disposition(
        "missing",
        LearningClassification.VOICE_PROFILE,
        LearningDispositionAction.INCORPORATE,
    )
    with pytest.raises(ValueError, match="unavailable"):
        write_learning_change_set(tmp_path / "missing.json", _selection(incorporated), [])
    with pytest.raises(ValueError, match="Researcher learning"):
        write_learning_change_set(
            tmp_path / "research.json",
            _selection(incorporated),
            [{"id": "missing", "role": "researcher", "principle": "Research only."}],
        )


def test_local_eligibility_hashes_only_available_authorised_artifacts(tmp_path):
    assert inspect_upgrade_eligibility(tmp_path, "author", {}) == {
        "eligible": False,
        "reason": "voice-not-active",
    }
    source = tmp_path / "source.md"
    source.write_text("A local authored source.", encoding="utf-8")
    order = tmp_path / "profiles/author/work-order.json"
    order.parent.mkdir(parents=True)
    order.write_text(
        json.dumps(
            {
                "display_name": "Author",
                "voice_id": "author",
                "authorisation": {"confirmed": True},
                "documents": [str(source), str(tmp_path / "missing.md")],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    publication = tmp_path / "content/published.md"
    publication.parent.mkdir(parents=True)
    publication.write_text("An approved publication.", encoding="utf-8")
    receipts = tmp_path / "publication-receipts"
    receipts.mkdir()
    (receipts / "accepted.receipt.json").write_text(
        json.dumps({"voice_id": "author", "artifact_path": "content/published.md"}),
        encoding="utf-8",
    )
    (receipts / "other.receipt.json").write_text(
        json.dumps({"voice_id": "other", "artifact_path": "content/published.md"}),
        encoding="utf-8",
    )
    (receipts / "missing.receipt.json").write_text(
        json.dumps({"voice_id": "author", "artifact_path": "content/missing.md"}),
        encoding="utf-8",
    )
    assert len(_local_evidence_hashes(tmp_path, "author")) == 2


def test_epoch_transition_rollback_restores_existing_files(tmp_path):
    prior = tmp_path / "profiles/author/learnings/1.0.0/memory.json"
    prior.parent.mkdir(parents=True)
    prior.write_text(
        json.dumps(
            {
                "voice_id": "author",
                "voice_version": "1.0.0",
                "created_at": "2026-08-22T00:00:00+00:00",
                "records": [{"id": "carry", "status": "active"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    resulting = tmp_path / "profiles/author/learnings/2.0.0/memory.json"
    resulting.parent.mkdir(parents=True)
    resulting.write_text("existing-result\n", encoding="utf-8")
    selection = _selection(
        _disposition(
            "carry",
            LearningClassification.REMAIN_LEARNING,
            LearningDispositionAction.CARRY_FORWARD,
        )
    )
    transition = prepare_epoch_transition(
        tmp_path,
        "author",
        "1.0.0",
        "2.0.0",
        "sha256:candidate",
        selection,
    )
    original_prior = prior.read_text(encoding="utf-8")
    transition.apply()
    assert transition.receipt.carried_forward_learning_ids == ["carry"]
    transition.rollback()
    assert json.loads(prior.read_text(encoding="utf-8")) == json.loads(original_prior)
    assert resulting.read_text(encoding="utf-8").strip() == "existing-result"


def test_epoch_transition_compensates_a_failed_first_write(tmp_path, monkeypatch):
    transition = prepare_epoch_transition(
        tmp_path,
        "author",
        None,
        "1.0.0",
        "sha256:candidate",
        None,
    )

    def fail_write(_path, _contents):
        raise OSError("simulated write failure")

    monkeypatch.setattr(RunStore, "_atomic_text", fail_write)
    with pytest.raises(OSError, match="simulated"):
        transition.apply()
    assert not transition.resulting_path.exists()
