import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.domain import AuthorContribution, RunStatus, WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.perspective_evaluation import evaluate_perspective_output
from content_creator.perspectives import (
    PerspectiveEntry,
    PerspectiveEntryStatus,
    PerspectiveError,
    PerspectiveProposalStore,
    PerspectiveProvenance,
    PerspectiveRegistry,
)
from content_creator.prompting import PromptAssembler
from content_creator.providers import FakeProvider, ProviderRegistry


def _entry(statement, entry_id):
    return PerspectiveEntry(
        id=entry_id,
        type="principle",
        statement=statement,
        topics=["training"],
        qualifications=["Apply proportionately."],
        provenance=[
            PerspectiveProvenance(
                kind="direct_author_input",
                reference="author interview",
            )
        ],
    )


def _activate_context(project, context, statement, entry_id):
    registry = PerspectiveRegistry(project, "default")
    registry.stage(context, [_entry(statement, entry_id)])
    return registry.activate(context, "Owner")


def test_perspective_activation_is_versioned_idempotent_and_tamper_evident(project):
    registry = PerspectiveRegistry(project, "default")
    manifest = registry.stage(
        "legal-training",
        [_entry("Teach recognition and escalation.", "training-001")],
    )
    assert manifest.status.value == "awaiting_approval"
    first = registry.activate("legal-training", "Owner")
    repeated = registry.activate("legal-training", "Owner")

    assert first == repeated
    assert first.activated_version == "1.0.0"
    resolved = registry.resolve("legal-training")
    assert resolved["active_entry_ids"] == ["training-001"]

    profile = project / resolved["path"] / "perspective.md"
    profile.write_text("tampered", encoding="utf-8")
    with pytest.raises(PerspectiveError, match="hash mismatch"):
        registry.resolve("legal-training")


def test_approved_entry_without_provenance_is_rejected(project):
    with pytest.raises(PerspectiveError, match="require provenance"):
        PerspectiveRegistry(project, "default").stage(
            "legal-training",
            [
                PerspectiveEntry(
                    id="unsupported-001",
                    statement="An unsupported position.",
                )
            ],
        )


def test_contexts_are_strictly_isolated_in_storage_and_prompts(project):
    _activate_context(
        project,
        "legal-training",
        "Training should teach recognition and escalation.",
        "training-001",
    )
    _activate_context(
        project,
        "space-law",
        "Autonomous systems raise unresolved liability questions.",
        "space-001",
    )

    prompts = PromptAssembler(project)
    legal = prompts.system_prompt(
        "writer",
        WorkOrder(
            request="write",
            topic="training",
            perspective_context="legal-training",
        ),
    )
    space = prompts.system_prompt(
        "writer",
        WorkOrder(
            request="write",
            topic="space",
            perspective_context="space-law",
        ),
    )
    neutral = prompts.system_prompt(
        "writer",
        WorkOrder(request="write", topic="neutral"),
    )

    assert "recognition and escalation" in legal
    assert "liability questions" not in legal
    assert "liability questions" in space
    assert "recognition and escalation" not in space
    assert "Perspective Context" not in neutral


def test_explicit_entry_selection_excludes_other_entries_in_same_context(project):
    registry = PerspectiveRegistry(project, "default")
    registry.stage(
        "legal-training",
        [
            _entry("Teach recognition and escalation.", "training-001"),
            _entry("Prefer scenario-led assessment.", "training-002"),
        ],
    )
    registry.activate("legal-training", "Owner")
    prompt = PromptAssembler(project).system_prompt(
        "writer",
        WorkOrder(
            request="write",
            topic="training",
            perspective_context="legal-training",
            author_contribution=AuthorContribution(
                supplied_by_author=True,
                reusable_perspective_entry_ids=["training-002"],
            ),
        ),
    )

    assert "scenario-led assessment" in prompt
    assert "recognition and escalation" not in prompt


def test_deactivation_blocks_new_use_but_preserves_historical_resolution(project):
    registry = PerspectiveRegistry(project, "default")
    _activate_context(
        project,
        "space-law",
        "Treat expertise boundaries explicitly.",
        "space-001",
    )
    registry.deactivate("space-law", "context withdrawn")

    with pytest.raises(PerspectiveError, match="not active"):
        registry.resolve("space-law")
    assert registry.resolve("space-law", "1.0.0", allow_inactive=True)["version"] == "1.0.0"


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_run_pins_perspective_and_provider_receives_same_contract(project, provider):
    _activate_context(
        project,
        "legal-training",
        "Training should teach recognition and escalation.",
        "training-001",
    )
    fake = FakeProvider(
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
        }
    )
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry({provider: fake}),
    )
    state = orchestrator.start(
        WorkOrder(
            request="Create neutral explanatory training material.",
            topic="Training",
            content_pack="general-text",
            format="text",
            provider=provider,
            perspective_context="legal-training",
            author_contribution=AuthorContribution(
                thesis="People should recognise when to escalate.",
                supplied_by_author=True,
            ),
            pack_options={"length": "50:600"},
        )
    )
    context = json.loads((project / "runs" / state.id / "resolved-context.json").read_text())
    provenance = json.loads((project / "runs" / state.id / "claim-provenance.json").read_text())

    assert state.status == RunStatus.READY
    assert state.work_order.resolved_perspective
    assert context["perspective"]["context_id"] == "legal-training"
    assert context["perspective"]["version"] == "1.0.0"
    assert context["perspective"]["active_entry_ids"] == ["training-001"]
    assert provenance["author_contribution"]["supplied_by_author"]
    writer_request = next(item for item in fake.requests if item.role == "writer")
    assert "recognition and escalation" in writer_request.system


def test_unknown_perspective_context_fails_before_run_creation(project):
    orchestrator = Orchestrator(project)
    with pytest.raises(PerspectiveError, match="Unknown perspective context"):
        orchestrator.start(
            WorkOrder(
                request="write",
                topic="topic",
                perspective_context="missing",
            )
        )
    assert not list((project / "runs").glob("*/state.json"))


def test_perspective_output_requires_author_evidence_for_first_person_position(project):
    unsupported = evaluate_perspective_output(
        project,
        WorkOrder(request="write", topic="topic"),
        "I believe this is the right approach.",
    )
    supplied = evaluate_perspective_output(
        project,
        WorkOrder(
            request="write",
            topic="topic",
            author_contribution=AuthorContribution(
                thesis="This is the right approach.",
                supplied_by_author=True,
            ),
        ),
        "I believe this is the right approach.",
    )

    assert not unsupported["passed"]
    assert supplied["passed"]


def test_publication_creates_only_context_scoped_candidate_then_requires_approval(
    project,
):
    _activate_context(
        project,
        "space-law",
        "Expertise boundaries should be explicit.",
        "space-001",
    )
    _activate_context(
        project,
        "legal-training",
        "Training should teach recognition.",
        "training-001",
    )
    extraction = {
        "candidates": [
            {
                "change_type": "new",
                "type": "interpretation",
                "statement": "Autonomy complicates established liability analysis.",
                "topics": ["space-law"],
                "qualifications": ["The position remains exploratory."],
                "counterpositions": [],
                "evidence": "The approved publication states this directly.",
                "confidence": 0.8,
            }
        ],
        "author_signal": "publication_approval",
    }
    fake = FakeProvider(
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
            "learning-extractor": [{"candidates": []}],
            "perspective-extractor": [extraction],
        }
    )
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": fake}),
    )
    state = orchestrator.start(
        WorkOrder(
            request="Create a space-law explanation.",
            topic="Space autonomy",
            content_pack="general-text",
            format="text",
            perspective_context="space-law",
            pack_options={"length": "50:600"},
        )
    )
    state = orchestrator.publish(state.id, filename="space.md")
    proposals = PerspectiveProposalStore(project, "default", "space-law").list()
    legal_entries = PerspectiveRegistry(project, "default").current_entries("legal-training")
    space_before = PerspectiveRegistry(project, "default").resolve("space-law")

    assert state.status == RunStatus.PUBLISHED
    assert len(proposals) == 1
    assert proposals[0]["status"] == "candidate"
    assert space_before["version"] == "1.0.0"
    assert [item.id for item in legal_entries] == ["training-001"]

    registry = PerspectiveRegistry(project, "default")
    registry.stage_proposal("space-law", proposals[0]["id"])
    receipt = registry.activate("space-law", "Owner")
    space_entries = registry.current_entries("space-law")
    legal_entries_after = registry.current_entries("legal-training")

    assert receipt.activated_version == "2.0.0"
    assert {item.statement for item in space_entries} == {
        "Expertise boundaries should be explicit.",
        "Autonomy complicates established liability analysis.",
    }
    assert [item.id for item in legal_entries_after] == ["training-001"]


def test_retirement_creates_candidate_and_preserves_historical_version(project):
    registry = PerspectiveRegistry(project, "default")
    _activate_context(
        project,
        "space-law",
        "An exploratory position.",
        "space-001",
    )
    registry.retire_entry("space-law", "space-001", "Author changed position")
    receipt = registry.activate("space-law", "Owner")
    current = registry.current_entries("space-law")
    historical = registry.resolve("space-law", "1.0.0")

    assert receipt.activated_version == "2.0.0"
    assert current[0].status == PerspectiveEntryStatus.RETIRED
    assert historical["active_entry_ids"] == ["space-001"]
