"""Build privacy-safe publication learning assessments."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .domain import RunState


def build_publication_assessment(
    root: Path,
    state: RunState,
    run_id: str,
    target: Path,
    feedback: Optional[str],
) -> Dict[str, Any]:
    """Return normalized evidence for post-publication learning.

    Args:
        root (Path): The workspace root directory.
        state (RunState): Published run state.
        run_id (str): Stable run identifier.
        target (Path): Repository-local publication target.
        feedback (Optional[str]): Explicit author feedback. Defaults to ``None``.

    Returns:
        Dict[str, Any]: Privacy-safe publication assessment evidence.
    """
    return {
        "run_id": run_id,
        "published_path": str(target.relative_to(root)),
        "voice_id": state.work_order.voice_id,
        "voice_version": state.work_order.voice_version,
        "content_pack": state.work_order.content_pack,
        "perspective_context": state.work_order.perspective_context,
        "perspective_version": state.work_order.perspective_version,
        "perspective_selections": [
            selection.model_dump(mode="json")
            for selection in state.work_order.perspective_selections
        ],
        "author_signal": "explicit_feedback" if feedback else "publication_approval",
        "feedback": feedback,
        "questions": {
            "plausibly_approvable": True,
            "passages_not_in_voice": None,
            "exaggerated_habit": None,
            "invented_experience": None,
            "channel_appropriate": True,
            "perspective_authentic": None,
            "unsupported_author_position": None,
            "perspective_qualifications_preserved": None,
            "research_conflicts_surfaced": None,
            "claim_provenance_clear": None,
        },
    }
