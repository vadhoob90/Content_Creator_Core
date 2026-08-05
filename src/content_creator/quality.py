"""Provide quality capabilities."""

from __future__ import annotations

from typing import Any, Dict, List

from .domain import (
    Critique,
    IssueSeverity,
    PriorIssueDisposition,
    QualityDecision,
)


def evaluate_quality(
    critique: Critique, core_rubric: Dict[str, Any], validation_errors: List[str]
) -> QualityDecision:
    """Evaluate quality."""
    dimensions = core_rubric["dimensions"]
    gate = core_rubric["quality_gate"]
    reasons = []
    weighted = 0.0
    minimum = 10.0

    for name, settings in dimensions.items():
        score = float(critique.scores.get(name, 0))
        minimum = min(minimum, score)
        weighted += score * float(settings["weight"])
        if score < float(settings["minimum_to_pass"]):
            reasons.append("{} score is below {}".format(name, settings["minimum_to_pass"]))

    blocking = sum(issue.severity == IssueSeverity.BLOCKING for issue in critique.issues)
    substantive = sum(issue.severity == IssueSeverity.SUBSTANTIVE for issue in critique.issues)
    minor = sum(issue.severity == IssueSeverity.MINOR for issue in critique.issues)
    unresolved = [
        key
        for key, disposition in critique.prior_issue_status.items()
        if disposition.status
        not in {
            PriorIssueDisposition.RESOLVED,
            PriorIssueDisposition.AUTHOR_REJECTED,
        }
    ]

    if validation_errors and gate.get("require_deterministic_validation", True):
        reasons.extend(validation_errors)
    if blocking > int(gate["blocking_issues_allowed"]):
        reasons.append("{} blocking issue(s) remain".format(blocking))
    if substantive > int(gate["substantive_issues_allowed"]):
        reasons.append("{} substantive issue(s) remain".format(substantive))
    if minor > int(gate["maximum_minor_issues"]):
        reasons.append("{} minor issues exceed the limit".format(minor))
    if weighted < float(gate["minimum_weighted_score"]):
        reasons.append(
            "weighted score {:.2f} is below {}".format(weighted, gate["minimum_weighted_score"])
        )
    if unresolved and gate.get("require_previous_issues_resolved_or_author_rejected", True):
        reasons.append("prior issues remain unresolved: {}".format(", ".join(unresolved)))

    critique.weighted_score = round(weighted, 2)
    return QualityDecision(
        passed=not reasons,
        weighted_score=round(weighted, 2),
        minimum_score=minimum,
        minor_issue_count=minor,
        reasons=reasons,
    )
