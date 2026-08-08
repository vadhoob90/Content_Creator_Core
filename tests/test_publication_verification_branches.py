import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.domain import WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.publication_provenance import PublicationProvenance


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
