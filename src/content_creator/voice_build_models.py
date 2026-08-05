"""Models and deterministic sampling helpers for the voice-build pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from .voices import SourceRecord, VoicePattern, VoiceWorkOrder


class VoiceBuildError(RuntimeError):
    """Report voice build failures."""

    pass


class VoiceAnalysis(BaseModel):
    """Capture one agent's analysis of voice evidence."""

    summary: str
    patterns: List[VoicePattern] = Field(default_factory=list)


class ProfileCriticism(BaseModel):
    """Represent a profile criticism."""

    rejected_pattern_ids: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class VoiceEvaluationJudgement(BaseModel):
    """Represent a voice evaluation judgement."""

    passed: bool
    scores: dict = Field(default_factory=dict)
    hard_failures: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


def analysis_excerpt(text: str, limit: int = 6000) -> str:
    """Return the analysis excerpt."""
    if len(text) <= limit:
        return text
    section = limit // 3
    midpoint = len(text) // 2
    middle_start = max(0, midpoint - section // 2)
    return "\n\n[...]\n\n".join(
        (text[:section], text[middle_start : middle_start + section], text[-section:])
    )


def even_sample(records: List[SourceRecord], limit: int) -> List[SourceRecord]:
    """Return the even sample."""
    if limit <= 0:
        return []
    if limit == 1:
        return [records[-1]]
    if len(records) <= limit:
        return list(records)
    return [records[round(index * (len(records) - 1) / (limit - 1))] for index in range(limit)]


def public_locator(locator: str) -> str:
    """Return the public locator."""
    return (
        locator
        if locator.startswith(("http://", "https://"))
        else f"local-document:{Path(locator).name}"
    )


@dataclass
class BuildState:
    """Represent a build state."""

    order: VoiceWorkOrder
    voice_root: Path
    candidate: Path
    final_candidate: Path
    cache: Path
    sources: List[SourceRecord] = field(default_factory=list)
    analysis_texts: dict[str, str] = field(default_factory=dict)
    normalized_sources: List[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    corpus: dict = field(default_factory=dict)
    held_out: List[SourceRecord] = field(default_factory=list)
    analysis_records: List[SourceRecord] = field(default_factory=list)
    signature: dict = field(default_factory=dict)
    patterns: List[VoicePattern] = field(default_factory=list)
    analysis_artifact: Optional[dict] = None
    criticism_artifact: Optional[dict] = None
