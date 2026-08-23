"""Persist hash-bound voice-upgrade artifacts into a staged candidate."""

from __future__ import annotations

import json
from pathlib import Path

from ..storage import RunStore
from .models import VoiceUpgradeBuildContext


def write_upgrade_artifacts(candidate: Path, context: VoiceUpgradeBuildContext) -> None:
    """Write complete plan, evidence, selection, and disposition evidence.

    Args:
        candidate (Path): Staged candidate directory.
        context (VoiceUpgradeBuildContext): Validated governed upgrade context.

    Returns:
        None: Upgrade artifacts are written before manifest hashing.
    """
    artifacts = {
        "voice-upgrade-plan.json": context.plan.model_dump_json(indent=2),
        "evidence-baseline.json": context.represented_evidence.model_dump_json(indent=2),
        "evidence-delta.json": context.evidence_delta.model_dump_json(indent=2),
        "learning-selection.json": context.learning_selection.model_dump_json(indent=2),
        "learning-dispositions.json": json.dumps(
            {
                "schema_version": "1.0",
                "voice_id": context.plan.voice_id,
                "baseline_version": context.plan.baseline_version,
                "dispositions": [
                    item.model_dump(mode="json") for item in context.learning_selection.dispositions
                ],
            },
            indent=2,
        ),
    }
    for filename, contents in artifacts.items():
        RunStore._atomic_text(candidate / filename, contents)
