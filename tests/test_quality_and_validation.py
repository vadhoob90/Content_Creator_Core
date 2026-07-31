import pytest
from conftest import passing_critique, valid_draft

from content_creator.configuration import Configuration
from content_creator.domain import (
    Critique,
    PriorIssueDisposition,
    WorkOrder,
)
from content_creator.quality import evaluate_quality
from content_creator.validation import validate_draft


def test_quality_gate_recomputes_weighted_score(project):
    critique = Critique.model_validate(passing_critique())
    critique.weighted_score = 1
    decision = evaluate_quality(critique, Configuration(project).rubric("core"), [])
    assert decision.passed
    assert decision.weighted_score == 9
    assert critique.weighted_score == 9


def test_blocking_issue_fails_even_with_high_scores(project):
    issue = {
        "dimension": "evidence_integrity",
        "severity": "blocking",
        "description": "Unsupported claim",
        "requested_change": "Remove or source it",
    }
    critique = Critique.model_validate(passing_critique(10, [issue]))
    decision = evaluate_quality(critique, Configuration(project).rubric("core"), [])
    assert not decision.passed
    assert any("blocking" in reason for reason in decision.reasons)


@pytest.mark.parametrize("status", ["resolved", "author_rejected"])
def test_structured_prior_issue_disposition_with_note_passes(project, status):
    critique = Critique.model_validate(
        passing_critique(
            prior={
                "legal_boundary": {
                    "status": status,
                    "note": "The author supplied an explicit disposition.",
                }
            }
        )
    )

    decision = evaluate_quality(
        critique, Configuration(project).rubric("core"), []
    )

    assert decision.passed
    assert critique.prior_issue_status["legal_boundary"].status == status


def test_structured_unresolved_prior_issue_fails(project):
    critique = Critique.model_validate(
        passing_critique(
            prior={
                "legal_boundary": {
                    "status": "unresolved",
                    "note": "The boundary remains too broad.",
                }
            }
        )
    )

    decision = evaluate_quality(
        critique, Configuration(project).rubric("core"), []
    )

    assert not decision.passed
    assert decision.reasons == [
        "prior issues remain unresolved: legal_boundary"
    ]


@pytest.mark.parametrize(
    ("legacy", "expected", "passes"),
    [
        (
            "Resolved. The proposition is now expressly limited.",
            PriorIssueDisposition.RESOLVED,
            True,
        ),
        (
            "Author rejected. Retain the deliberate formulation.",
            PriorIssueDisposition.AUTHOR_REJECTED,
            True,
        ),
        ("Unresolved. The boundary is still unclear.", PriorIssueDisposition.UNRESOLVED, False),
        ("Not resolved despite revision.", PriorIssueDisposition.UNRESOLVED, False),
        ("Needs another look.", PriorIssueDisposition.UNRESOLVED, False),
    ],
)
def test_legacy_prior_issue_status_is_normalised_fail_safe(
    project, legacy, expected, passes
):
    critique = Critique.model_validate(
        passing_critique(prior={"legal_boundary": legacy})
    )

    decision = evaluate_quality(
        critique, Configuration(project).rubric("core"), []
    )

    disposition = critique.prior_issue_status["legal_boundary"]
    assert disposition.status == expected
    assert disposition.note == legacy
    assert decision.passed is passes


def test_mechanical_validation():
    order = WorkOrder(
        request="x", topic="x", pack_options={"length": "50:600"}
    )
    errors = validate_draft(
        "Too short — #growth",
        order,
        ["word-count", "no-em-dash", "no-hashtags"],
    )
    assert "Em dashes are not allowed" in errors
    assert "Hashtags are not allowed" in errors
    assert any("between 50 and 600" in error for error in errors)


def test_banned_phrases_come_from_pack_options():
    order = WorkOrder(
        request="x",
        topic="x",
        pack_options={"banned_phrases": ["workspace-specific phrase"]},
    )

    assert validate_draft(
        "A workspace-specific phrase appears.", order, ["banned-phrase"]
    ) == ["Banned phrase: workspace-specific phrase"]


def test_valid_researched_post_has_link():
    order = WorkOrder(
        request="x",
        topic="x",
        research_depth="light",
        research_source="agent",
    )
    assert validate_draft(valid_draft(researched=True), order) == []
