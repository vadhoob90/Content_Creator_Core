from __future__ import annotations

import re
from typing import List

from .domain import ContentFormat, ResearchBrief, ResearchDepth, WorkOrder

BANNED_PHRASES = (
    "in today's fast-paced world",
    "game-changer",
    "let that sink in",
    "unlock the power",
)


def validate_draft(draft: str, order: WorkOrder) -> List[str]:
    errors = []
    words = re.findall(r"\b[\w’'-]+\b", draft)
    lowered = draft.lower()

    if "—" in draft:
        errors.append("Em dashes are not allowed")
    if re.search(r"(?<!\w)#\w+", draft):
        errors.append("Hashtags are not allowed")
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            errors.append("Banned phrase: {}".format(phrase))

    if order.format == ContentFormat.ARTICLE and not 800 <= len(words) <= 1800:
        errors.append("Article must be between 800 and 1800 words")
    if order.format == ContentFormat.POST and not 50 <= len(words) <= 600:
        errors.append("Post must be between 50 and 600 words")
    if order.research_depth != ResearchDepth.NONE and not re.search(
        r"https?://|]\(https?://", draft
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
                errors.append("Evidence item {} references an unknown source".format(index))
    return errors
