from __future__ import annotations

import re

from .voices import AttributionResult


def classify_attribution(text: str, display_name: str, kind: str) -> AttributionResult:
    escaped = re.escape(display_name)
    first = re.escape(display_name.split()[0])
    if re.search(r"written by[^\n.]*" + escaped + r"[^\n.]*(?:and|&)", text, re.I):
        return AttributionResult(
            classification="co_authored",
            confidence=0.8,
            voice_weight=0.65,
            evidence=["Co-authorship marker includes the requested person"],
        )
    if re.search(r"(?:by|author[:\s]+)\s*" + escaped, text, re.I):
        return AttributionResult(
            classification="directly_authored",
            confidence=0.95,
            voice_weight=1.0,
            evidence=["Visible author or byline matches the requested person"],
        )
    if kind == "transcript" and re.search(r"(?:^|\s)" + first + r"\s*:", text, re.I):
        return AttributionResult(
            classification="interview",
            confidence=0.85,
            voice_weight=0.5,
            evidence=["Transcript contains speaker-labelled contributions"],
        )
    if re.search(escaped, text, re.I):
        return AttributionResult(
            classification="person_as_subject",
            confidence=0.65,
            voice_weight=0.0,
            evidence=["Person is mentioned but authorship is not established"],
            needs_human_review=True,
        )
    return AttributionResult(
        classification="uncertain",
        confidence=0.2,
        voice_weight=0.0,
        evidence=["No reliable authorship evidence was found"],
        needs_human_review=True,
    )
