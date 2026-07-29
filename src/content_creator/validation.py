from __future__ import annotations

import re
from typing import List, Optional

from .domain import ResearchBrief, ResearchDepth, WorkOrder


def validate_draft(
    draft: str, order: WorkOrder, validators: Optional[List[str]] = None
) -> List[str]:
    errors = []
    enabled = set(
        validators
        or [
            "word-count",
            "citation-integrity",
        ]
    )
    words = re.findall(r"\b[\w’'-]+\b", draft)
    lowered = draft.lower()

    if "no-em-dash" in enabled and "—" in draft:
        errors.append("Em dashes are not allowed")
    if "no-hashtags" in enabled and re.search(r"(?<!\w)#\w+", draft):
        errors.append("Hashtags are not allowed")
    if "banned-phrase" in enabled:
        phrases = order.pack_options.get("banned_phrases", [])
        if isinstance(phrases, str):
            phrases = [phrases]
        for phrase in phrases:
            if str(phrase).lower() in lowered:
                errors.append("Banned phrase: {}".format(phrase))

    length = order.pack_options.get("length")
    if (
        "word-count" in enabled
        and isinstance(length, str)
        and re.fullmatch(r"\d+:\d+", length)
    ):
        minimum, maximum = (int(item) for item in length.split(":"))
        if not minimum <= len(words) <= maximum:
            errors.append(
                "Content must be between {} and {} words".format(minimum, maximum)
            )
    if (
        "citation-integrity" in enabled
        and order.research_depth != ResearchDepth.NONE
        and not re.search(r"https?://|]\(https?://", draft)
    ):
        errors.append("Research-backed drafts must include at least one source link")
    return errors


def validate_research_brief(brief: ResearchBrief) -> List[str]:
    errors = []
    known_urls = {source.url for source in brief.sources}
    for source in brief.sources:
        if not source.url.startswith(("https://", "http://")):
            errors.append("Source URL is not absolute: {}".format(source.url))
    for index, evidence in enumerate(brief.evidence, start=1):
        if not evidence.source_urls:
            errors.append("Evidence item {} has no source".format(index))
        for url in evidence.source_urls:
            if url not in known_urls:
                errors.append(
                    "Evidence item {} references an unknown source".format(index)
                )
    return errors
