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


def isolate_attributed_text(
    text: str,
    display_name: str,
    attribution: AttributionResult,
    kind: str,
) -> tuple[str, str]:
    """Conservatively isolate analysable language without claiming authorship."""

    cleaned = text.strip()
    if attribution.classification == "directly_authored":
        cleaned = re.sub(
            r"^\s*(?:written\s+by|by|author[:\s]+)\s*"
            + re.escape(display_name)
            + r"\s*[.,:;—-]*\s*",
            "",
            cleaned,
            count=1,
            flags=re.I,
        )
        return cleaned, "full-source-with-byline-removed"

    if kind == "transcript" and attribution.classification == "interview":
        names = {display_name.lower(), display_name.split()[0].lower()}
        selected = []
        active = False
        saw_speaker_label = False
        for line in cleaned.splitlines():
            match = re.match(r"^\s*([^:\n]{1,80})\s*:\s*(.*)$", line)
            if match:
                saw_speaker_label = True
                active = match.group(1).strip().lower() in names
                if active and match.group(2).strip():
                    selected.append(match.group(2).strip())
            elif active and line.strip():
                selected.append(line.strip())
        if selected:
            return "\n\n".join(selected), "speaker-turns-only"
        if saw_speaker_label:
            return "", "no-attributed-speaker-turns"

    scope = (
        "shared-source-weighted"
        if attribution.classification == "co_authored"
        else "full-source"
    )
    return cleaned, scope
