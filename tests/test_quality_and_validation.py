from conftest import passing_critique, valid_draft

from content_creator.configuration import Configuration
from content_creator.domain import Critique, WorkOrder
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


def test_mechanical_validation():
    order = WorkOrder(request="x", topic="x")
    errors = validate_draft("Too short — #growth", order)
    assert "Em dashes are not allowed" in errors
    assert "Hashtags are not allowed" in errors
    assert any("between 50 and 600" in error for error in errors)


def test_valid_researched_post_has_link():
    order = WorkOrder(
        request="x",
        topic="x",
        research_depth="light",
        research_source="agent",
    )
    assert validate_draft(valid_draft(researched=True), order) == []
