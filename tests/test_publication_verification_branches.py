import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.domain import WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.publication_provenance import (
    PublicationProvenance,
    PublicationProvenanceError,
)


def _published_receipt(project, filename="verified.md"):
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry(
            {
                "anthropic": FakeProvider(
                    {
                        "writer": [valid_draft()],
                        "critic": [passing_critique()],
                        "learning-extractor": [{"candidates": []}],
                    }
                )
            }
        ),
    )
    state = orchestrator.start(
        WorkOrder(
            request="Explain a neutral workflow.",
            topic="Neutral workflow",
            pack_options={"length": "50:600"},
        )
    )
    orchestrator.publish(state.id, filename=filename)
    return (
        project
        / "publication-receipts"
        / "content"
        / "general-text"
        / "published"
        / f"{filename}.receipt.json"
    )


def _required(project):
    return PublicationProvenance(
        project,
        {"policy": "required", "receipts_directory": "publication-receipts"},
    )


def test_verifier_rejects_malformed_receipt_without_masking_other_publications(project):
    receipt_path = _published_receipt(project)
    receipt_path.write_text("not-json", encoding="utf-8")

    report = _required(project).verify()

    assert report["status"] == "failed"
    assert [finding["code"] for finding in report["findings"]] == ["invalid_receipt"]


def test_verifier_reports_independent_tampered_receipt_safety_failures(project):
    receipt_path = _published_receipt(project)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["artifact_path"] = "content/general-text/published/missing.md"
    receipt["final_status"] = "ready"
    receipt["author_contribution_provenance"] = "none"
    receipt["perspective_evaluation"].update(
        {
            "passed": False,
            "errors": ["deterministic evaluation failed"],
            "position_marker_count": 1,
        }
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = _required(project).verify()
    codes = {finding["code"] for finding in report["findings"]}

    assert {
        "artifact_path_mismatch",
        "missing_artifact",
        "invalid_originating_status",
        "failed_perspective_evaluation",
        "missing_authorial_provenance",
    } <= codes


@pytest.mark.parametrize(
    ("semantic_review", "expected_code"),
    [
        ({"status": "review_required"}, "unresolved_semantic_review"),
        (
            {"status": "passed", "review_required_codes": ["omitted_qualification"]},
            "inconsistent_semantic_review",
        ),
        ({"status": "author_approved"}, "missing_semantic_review_decision"),
        ({"status": "unexpected"}, "invalid_semantic_review_status"),
    ],
)
def test_verifier_fails_closed_for_invalid_semantic_review_states(
    project,
    semantic_review,
    expected_code,
):
    receipt_path = _published_receipt(project)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["semantic_review"] = semantic_review
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = _required(project).verify()

    assert expected_code in {finding["code"] for finding in report["findings"]}


def test_disabled_verification_does_not_inventory_publications(project):
    service = PublicationProvenance(
        project, {"policy": "off", "receipts_directory": "publication-receipts"}
    )

    assert service.verify()["status"] == "disabled"


@pytest.mark.parametrize("artifact", ["../outside.md", "/tmp/outside.md"])
def test_receipt_paths_cannot_leave_the_workspace(project, artifact):
    with pytest.raises(PublicationProvenanceError, match="must stay in workspace"):
        _required(project).receipt_path(artifact)


def test_publication_baseline_requires_explicit_replacement(project):
    publication = project / "content" / "general-text" / "published" / "legacy.md"
    publication.parent.mkdir(parents=True, exist_ok=True)
    publication.write_text("legacy", encoding="utf-8")
    service = _required(project)

    first = service.write_baseline()
    with pytest.raises(PublicationProvenanceError, match="already exists"):
        service.write_baseline()
    replaced = service.write_baseline(replace=True)

    assert first["artifact_count"] == replaced["artifact_count"] == 1


def test_verifier_reports_receipts_without_publications(project):
    receipt = project / "publication-receipts" / "orphan.md.receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}", encoding="utf-8")

    report = _required(project).verify()

    assert [finding["code"] for finding in report["findings"]] == ["orphan_receipt"]


def test_existing_receipt_blocks_a_publication_before_content_is_written(project):
    target = project / "content" / "general-text" / "published" / "collision.md"
    receipt = _required(project).receipt_path("content/general-text/published/collision.md")
    receipt.parent.mkdir(parents=True)
    receipt.write_text("reserved", encoding="utf-8")

    with pytest.raises(PublicationProvenanceError, match="Refusing to overwrite"):
        _required(project).ensure_receipt_available(target)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("voice_id", "unavailable-voice", "unavailable_voice"),
        ("voice_manifest_hash", "0" * 64, "voice_hash_mismatch"),
    ],
)
def test_verifier_rejects_unavailable_or_changed_voice_evidence(project, field, value, expected):
    receipt_path = _published_receipt(project)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt[field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = _required(project).verify()

    assert expected in {finding["code"] for finding in report["findings"]}
