"""Define publication verification policy and normalized findings."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from .domain import RunState


class PublicationProvenanceError(RuntimeError):
    """Report a deterministic publication-provenance failure."""


class PublicationPolicy(str, Enum):
    """Enumerate supported publication receipt enforcement levels."""

    OFF = "off"
    ADVISORY = "advisory"
    REQUIRED_FOR_NEW = "required-for-new-publications"
    REQUIRED = "required"


class PublicationFinding(BaseModel):
    """Describe one deterministic publication verification finding."""

    category: str = "deterministic_failure"
    code: str
    artifact_path: Optional[str] = None
    detail: str


def provenance_source(state: RunState) -> str:
    """Return the bounded author-contribution provenance classification.

    Args:
        state (RunState): Run whose author contribution is classified.

    Returns:
        str: Stable privacy-safe provenance label.
    """
    contribution = state.work_order.author_contribution
    direct = bool(
        contribution
        and contribution.supplied_by_author
        and (contribution.thesis or contribution.intended_challenge or contribution.personal_basis)
    )
    selected = bool(state.work_order.perspective_selections)
    if direct and selected:
        return "direct-and-selected-perspective"
    if direct:
        return "direct-author-contribution"
    if selected:
        return "selected-perspective"
    return "none"
