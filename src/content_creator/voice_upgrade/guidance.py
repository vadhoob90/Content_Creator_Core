"""Convert reviewed learning dispositions into explicit voice guidance."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from ..storage import RunStore
from ..voice_evolution import EvolutionResult
from .models import (
    LearningClassification,
    LearningDispositionAction,
    LearningSelection,
)


def write_learning_change_set(
    path: Path,
    selection: LearningSelection,
    records: list[dict[str, Any]],
    explicit_change_set: Optional[Path] = None,
) -> Path:
    """Write semantic voice proposals backed by selected learning provenance.

    Merge explicit author changes with eligible incorporated learning while rejecting
    research-role findings that must remain outside linguistic voice guidance.

    Args:
        path (Path): Destination for the combined semantic change set.
        selection (LearningSelection): Author-reviewed dispositions.
        records (list[dict[str, Any]]): Exact prior-epoch learning records.
        explicit_change_set (Optional[Path]): Additional author rule changes. Defaults to
            ``None``.

    Returns:
        Path: Written combined change-set path.

    Raises:
        ValueError: If selected learning provenance is unavailable or ineligible.
    """
    by_id = {str(record.get("id")): record for record in records}
    changes = []
    if explicit_change_set:
        changes.extend(json.loads(explicit_change_set.read_text(encoding="utf-8"))["changes"])
    for disposition in selection.dispositions:
        if disposition.disposition != LearningDispositionAction.INCORPORATE:
            continue
        record = by_id.get(disposition.learning_id)
        if not record:
            raise ValueError(
                "Selected learning record is unavailable: {}".format(disposition.learning_id)
            )
        if record.get("role") == "researcher":
            raise ValueError("Researcher learning cannot be incorporated into linguistic voice")
        pattern_id = disposition.target_guidance_id or "learning-{}".format(disposition.learning_id)
        category = {
            LearningClassification.VOICE_PROFILE: "reviewed-learning-profile",
            LearningClassification.VOICE_CONSTRAINT: "reviewed-learning-constraint",
            LearningClassification.CRITIC_RUBRIC: "reviewed-learning-rubric",
        }[disposition.classification]
        principle = str(record.get("principle", "")).strip()
        replacement = {
            "id": pattern_id,
            "name": "Reviewed learning: {}".format(principle[:72]),
            "description": principle,
            "status": "for-review",
            "confidence": disposition.confidence,
            "supporting_source_ids": ["learning:{}".format(disposition.learning_id)],
            "mandatory": disposition.classification == LearningClassification.VOICE_CONSTRAINT,
            "category": category,
            "generation_guidance": principle,
            "anti_pattern": "Do not broaden this reviewed rule beyond its recorded scope.",
        }
        changes.append(
            {
                "action": "modify" if disposition.target_guidance_id else "add",
                "target_id": disposition.target_guidance_id,
                "replacement": replacement,
                "evidence_source_ids": ["learning:{}".format(disposition.learning_id)],
                "confidence": disposition.confidence,
                "rationale": "{} Reviewed from learning {}: {}".format(
                    disposition.rationale,
                    disposition.learning_id,
                    principle,
                ),
            }
        )
    RunStore._atomic_text(
        path,
        json.dumps({"schema_version": "1.0", "changes": changes}, indent=2),
    )
    return path


def apply_learning_overlays(
    candidate: Path,
    evolved: EvolutionResult,
    selection: LearningSelection,
    records: list[dict[str, Any]],
) -> EvolutionResult:
    """Add reviewed constraint and critic counterparts to structured artifacts.

    Args:
        candidate (Path): Staged candidate directory.
        evolved (EvolutionResult): Baseline-preserving voice artifacts.
        selection (LearningSelection): Author-reviewed dispositions.
        records (list[dict[str, Any]]): Exact prior-epoch learning records.

    Returns:
        EvolutionResult: Updated profile, constraints, rubric, and patterns.
    """
    constraints = deepcopy(evolved.constraints)
    rubric = deepcopy(evolved.rubric)
    by_id = {str(record.get("id")): record for record in records}
    for disposition in selection.dispositions:
        if disposition.disposition != LearningDispositionAction.INCORPORATE:
            continue
        principle = str(by_id[disposition.learning_id].get("principle", "")).strip()
        if disposition.classification == LearningClassification.VOICE_CONSTRAINT:
            constraints.setdefault("reviewed_voice_constraints", {})[disposition.learning_id] = (
                principle
            )
        if disposition.classification == LearningClassification.CRITIC_RUBRIC:
            rubric.setdefault("reviewed_author_rules", {})[disposition.learning_id] = principle
    RunStore._atomic_text(candidate / "constraints.json", json.dumps(constraints, indent=2))
    RunStore._atomic_text(candidate / "voice-rubric.json", json.dumps(rubric, indent=2))
    return EvolutionResult(evolved.profile, constraints, rubric, evolved.patterns)
