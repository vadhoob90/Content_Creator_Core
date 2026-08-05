"""Provide attribution capabilities."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .voices import AttributionResult


def _names(author_name: str, aliases: Optional[Iterable[str]]) -> List[str]:
    """Return the names."""
    return list(
        dict.fromkeys(
            name.strip() for name in [author_name, *(aliases or [])] if name and name.strip()
        )
    )


def classify_attribution(
    text: str,
    author_name: str,
    kind: str,
    aliases: Optional[Iterable[str]] = None,
) -> AttributionResult:
    """Classify attribution."""
    names = _names(author_name, aliases)
    for name in names:
        escaped = re.escape(name)
        if re.search(
            r"written by[^\n.]*" + escaped + r"[^\n.]*(?:and|&)",
            text,
            re.I,
        ):
            return AttributionResult(
                classification="co_authored",
                confidence=0.8,
                voice_weight=0.65,
                evidence=["Co-authorship marker includes {}".format(name)],
            )
        if re.search(r"(?:by|author[:\s]+)\s*" + escaped, text, re.I):
            return AttributionResult(
                classification="directly_authored",
                confidence=0.95,
                voice_weight=1.0,
                evidence=["Visible author or byline matches {}".format(name)],
            )
    if kind == "transcript":
        first_names = [re.escape(name.split()[0]) for name in names]
        if any(re.search(r"(?:^|\s)" + first + r"\s*:", text, re.I) for first in first_names):
            return AttributionResult(
                classification="interview",
                confidence=0.85,
                voice_weight=0.5,
                evidence=["Transcript contains speaker-labelled contributions"],
            )
    if any(re.search(re.escape(name), text, re.I) for name in names):
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


def isolate_attributed_text(
    text: str,
    author_name: str,
    attribution: AttributionResult,
    kind: str,
    aliases: Optional[Iterable[str]] = None,
) -> tuple[str, str]:
    """Conservatively isolate analysable language without claiming authorship."""

    cleaned = text.strip()
    names = _names(author_name, aliases)
    if attribution.classification == "directly_authored":
        name_pattern = "(?:{})".format("|".join(re.escape(name) for name in names))
        cleaned = re.sub(
            r"^\s*(?:written\s+by|by|author[:\s]+)\s*" + name_pattern + r"\s*[.,:;—-]*\s*",
            "",
            cleaned,
            count=1,
            flags=re.I,
        )
        return cleaned, "full-source-with-byline-removed"

    if kind == "transcript" and attribution.classification == "interview":
        speaker_names = {
            value for name in names for value in (name.lower(), name.split()[0].lower())
        }
        selected = []
        active = False
        saw_speaker_label = False
        for line in cleaned.splitlines():
            match = re.match(r"^\s*([^:\n]{1,80})\s*:\s*(.*)$", line)
            if match:
                saw_speaker_label = True
                active = match.group(1).strip().lower() in speaker_names
                if active and match.group(2).strip():
                    selected.append(match.group(2).strip())
            elif active and line.strip():
                selected.append(line.strip())
        if selected:
            return "\n\n".join(selected), "speaker-turns-only"
        if saw_speaker_label:
            return "", "no-attributed-speaker-turns"

    scope = (
        "shared-source-weighted" if attribution.classification == "co_authored" else "full-source"
    )
    return cleaned, scope
