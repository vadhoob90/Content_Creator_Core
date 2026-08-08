import json

import pytest
import yaml
from conftest import passing_critique, valid_draft

from content_creator.cli import main
from content_creator.domain import AuthorContribution, WorkOrder
from content_creator.orchestrator import OrchestrationError, Orchestrator
from content_creator.perspectives import (
    PerspectiveEntry,
    PerspectiveProvenance,
    PerspectiveRegistry,
)
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.publication_provenance import PublicationProvenance


def _orchestrator(project, draft=None, extra=None):
    responses = {
        "writer": [draft or valid_draft()],
        "critic": [passing_critique()],
        "learning-extractor": [{"candidates": []}],
    }
    responses.update(extra or {})
    return Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": FakeProvider(responses)}),
    )


def _activate_perspective(project):
    registry = PerspectiveRegistry(project, "default")
    registry.stage(
        "legal-training",
        [
            PerspectiveEntry(
                id="training-001",
                statement="Training should teach recognition and escalation.",
                qualifications=["Apply proportionately."],
                provenance=[
                    PerspectiveProvenance(
                        kind="direct_author_input",
                        reference="author interview",
                    )
                ],
            )
        ],
    )
    registry.activate("legal-training", "Owner")


def _required(project):
    return PublicationProvenance(
        project,
        {"policy": "required", "receipts_directory": "publication-receipts"},
    )


def test_publication_writes_privacy_safe_receipt_for_direct_author_contribution(project):
    draft = "I believe careful escalation improves professional judgment.\n\n" + valid_draft()
    orchestrator = _orchestrator(project, draft=draft)
    state = orchestrator.start(
        WorkOrder(
            request="Create the training explanation.",
            topic="Training",
            author_contribution=AuthorContribution(
                thesis="Careful escalation improves professional judgment.",
                supplied_by_author=True,
            ),
            pack_options={"length": "50:600"},
        )
    )

    published = orchestrator.publish(state.id, filename="direct.md")
    receipt_path = (
        project / "publication-receipts/content/general-text/published/direct.md.receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert published.published_path == "content/general-text/published/direct.md"
    assert receipt["author_contribution_provenance"] == "direct-author-contribution"
    assert receipt["perspectives"] == []
    assert receipt["perspective_evaluation"]["passed"] is True
    assert "Careful escalation" not in json.dumps(receipt)
    assert _required(project).verify()["status"] == "ok"


def test_selected_perspective_receipt_pins_version_entries_and_hashes(project):
    _activate_perspective(project)
    orchestrator = _orchestrator(
        project,
        extra={"perspective-extractor": [{"candidates": []}]},
    )
    state = orchestrator.start(
        WorkOrder(
            request="Explain professional training.",
            topic="Training",
            perspective_context="legal-training",
            author_contribution=AuthorContribution(
                reusable_perspective_entry_ids=["training-001"],
                supplied_by_author=True,
            ),
            pack_options={"length": "50:600"},
        )
    )
    orchestrator.publish(state.id, filename="selected.md")
    receipt = json.loads(
        (
            project / "publication-receipts/content/general-text/published/selected.md.receipt.json"
        ).read_text(encoding="utf-8")
    )

    perspective = receipt["perspectives"][0]
    assert perspective["context_id"] == "legal-training"
    assert perspective["version"] == "1.0.0"
    assert perspective["status_at_publication"] == "active"
    assert perspective["selected_entry_hashes"]["training-001"].startswith("sha256:")
    assert _required(project).verify()["status"] == "ok"


def test_neutral_publication_needs_no_author_position_provenance(project):
    orchestrator = _orchestrator(project)
    state = orchestrator.start(
        WorkOrder(
            request="Explain a neutral workflow.",
            topic="Neutral workflow",
            pack_options={"length": "50:600"},
        )
    )
    orchestrator.publish(state.id, filename="neutral.md")

    report = _required(project).verify()
    assert report["status"] == "ok"
    assert report["findings"] == []


def test_verifier_rejects_changed_publication_and_missing_receipt(project):
    orchestrator = _orchestrator(project)
    state = orchestrator.start(
        WorkOrder(
            request="Explain a neutral workflow.",
            topic="Neutral workflow",
            pack_options={"length": "50:600"},
        )
    )
    orchestrator.publish(state.id, filename="changed.md")
    target = project / "content/general-text/published/changed.md"
    target.write_text("changed after publication", encoding="utf-8")
    missing = project / "content/general-text/published/unreceipted.md"
    missing.write_text("legacy or bypassed publication", encoding="utf-8")

    report = _required(project).verify()
    codes = {item["code"] for item in report["findings"]}

    assert report["status"] == "failed"
    assert {"artifact_hash_mismatch", "missing_receipt"} <= codes


def test_prospective_baseline_allows_legacy_but_detects_changes(project):
    legacy = project / "content/general-text/published/legacy.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("legacy", encoding="utf-8")
    service = PublicationProvenance(
        project,
        {
            "policy": "required-for-new-publications",
            "receipts_directory": "publication-receipts",
        },
    )

    result = service.write_baseline()
    assert result["artifact_count"] == 1
    assert service.verify()["status"] == "ok"

    legacy.write_text("modified legacy", encoding="utf-8")
    report = service.verify()
    assert report["status"] == "failed"
    assert report["findings"][0]["code"] == "missing_receipt"


def test_inactive_perspective_stops_publication_before_destination_write(project):
    _activate_perspective(project)
    orchestrator = _orchestrator(
        project,
        extra={"perspective-extractor": [{"candidates": []}]},
    )
    state = orchestrator.start(
        WorkOrder(
            request="Explain professional training.",
            topic="Training",
            perspective_context="legal-training",
            pack_options={"length": "50:600"},
        )
    )
    PerspectiveRegistry(project, "default").deactivate("legal-training", "withdrawn")

    with pytest.raises(OrchestrationError, match="not active"):
        orchestrator.publish(state.id, filename="blocked.md")

    assert not (project / "content/general-text/published/blocked.md").exists()
    stored = orchestrator.store.load(state.id)
    assert stored.status.value == "needs_author"
    assert stored.events[-1].name == "publication_provenance_failed"


def test_verify_publications_cli_returns_nonzero_for_enforced_finding(project, capsys):
    target = project / "content/general-text/published/bypassed.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("bypassed", encoding="utf-8")
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump(
            {
                "publication_provenance": {
                    "policy": "required",
                    "receipts_directory": "publication-receipts",
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(["--workspace", str(project), "verify-publications"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert report["findings"][0]["code"] == "missing_receipt"
