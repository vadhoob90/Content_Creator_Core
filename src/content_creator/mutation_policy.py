"""Plan mutation-test scope and validate survivor decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

ReleaseImpact = Literal["none", "patch", "minor", "major"]

CRITICAL_MODULES = {
    "src/content_creator/quality.py": "content_creator.quality.*",
    "src/content_creator/versioned_artifacts.py": "content_creator.versioned_artifacts.*",
}
VALID_CLASSIFICATIONS = {"test-gap", "equivalent", "tool-limitation"}


@dataclass(frozen=True)
class MutationPlan:
    """Describe the mutation work expected for one change."""

    impact: ReleaseImpact
    patterns: tuple[str, ...]
    required: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation.

        Returns:
            dict[str, Any]: Stable mutation-plan fields for scripts and CI.
        """
        return {
            "impact": self.impact,
            "patterns": list(self.patterns),
            "required": self.required,
            "reason": self.reason,
        }


def plan_mutation_scope(changed_files: list[str], impact: ReleaseImpact) -> MutationPlan:
    """Select configured mutants using semantic impact and critical-path risk.

    Args:
        changed_files (list[str]): Repository-relative paths changed by the proposal.
        impact (ReleaseImpact): Declared semantic release impact.

    Returns:
        MutationPlan: Target patterns, enforcement state, and selection rationale.
    """
    changed_critical = tuple(
        pattern for path, pattern in CRITICAL_MODULES.items() if path in changed_files
    )
    production_changed = any(path.startswith("src/content_creator/") for path in changed_files)

    if impact in {"minor", "major"}:
        return MutationPlan(
            impact,
            tuple(CRITICAL_MODULES.values()),
            True,
            f"{impact} changes exercise the complete configured critical-module set",
        )
    if changed_critical:
        return MutationPlan(
            impact,
            changed_critical,
            True,
            "the change touches a configured critical module",
        )
    if impact == "patch" and production_changed:
        return MutationPlan(
            impact,
            tuple(CRITICAL_MODULES.values()),
            True,
            "a production patch exercises the configured regression-risk set",
        )
    return MutationPlan(
        impact,
        (),
        False,
        "no configured critical module or release-risk trigger changed",
    )


def validate_waivers(path: Path, *, today: date | None = None) -> list[str]:
    """Return validation errors for mutation survivor decisions.

    Args:
        path (Path): YAML survivor-decision file to validate.
        today (date | None): Date used for expiry checks. Defaults to ``None``.

    Returns:
        list[str]: Stable validation errors, or an empty list when valid.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return ["schema_version must be 1"]
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return ["decisions must be a list"]

    errors: list[str] = []
    current = today or date.today()
    required = {"mutant", "classification", "rationale", "owner", "expires", "follow_up"}
    for index, decision in enumerate(decisions):
        prefix = f"decisions[{index}]"
        if not isinstance(decision, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        missing = sorted(required - decision.keys())
        if missing:
            errors.append(f"{prefix} is missing: {', '.join(missing)}")
            continue
        if decision["classification"] not in VALID_CLASSIFICATIONS:
            errors.append(f"{prefix}.classification is invalid")
        try:
            expiry = date.fromisoformat(str(decision["expires"]))
        except ValueError:
            errors.append(f"{prefix}.expires must use YYYY-MM-DD")
        else:
            if expiry < current:
                errors.append(f"{prefix} expired on {expiry.isoformat()}")
        for field in ("mutant", "rationale", "owner", "follow_up"):
            if not isinstance(decision[field], str) or not decision[field].strip():
                errors.append(f"{prefix}.{field} must be non-empty text")
    return errors
