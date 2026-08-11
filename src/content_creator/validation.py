"""Provide validation capabilities."""

from __future__ import annotations

import re
from typing import List, Optional

from .domain import ResearchBrief, ResearchDepth, WorkOrder

_DOCUMENT_FENCE = re.compile(r"^```(?:markdown|md)?\s*$", re.IGNORECASE)


def normalize_publishable_markdown(draft: str) -> str:
    """Remove a model-added fence around a publishable Markdown document.

    Internal code fences are preserved. A leading Markdown wrapper is removed even
    when the model omitted its closing fence so malformed wrapper syntax cannot reach
    the final draft.

    Args:
        draft (str): Model- or author-supplied Markdown.

    Returns:
        str: Normalized publishable Markdown.
    """
    lines = draft.strip().splitlines()
    if not lines or not _DOCUMENT_FENCE.fullmatch(lines[0].strip()):
        return draft.strip()
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def has_document_fence(draft: str) -> bool:
    """Return whether the complete draft begins with a Markdown wrapper fence.

    Args:
        draft (str): Markdown draft to inspect.

    Returns:
        bool: Whether a whole-document Markdown fence starts the draft.
    """
    lines = draft.strip().splitlines()
    return bool(lines and _DOCUMENT_FENCE.fullmatch(lines[0].strip()))


def _document_fence_errors(draft: str) -> List[str]:
    """Return deterministic errors for non-publishable document wrappers.

    Args:
        draft (str): Markdown draft to inspect.

    Returns:
        List[str]: Validation errors for a whole-document wrapper.
    """
    if has_document_fence(draft):
        return ["Draft must not be wrapped in a Markdown code fence"]
    return []


def validate_draft(
    draft: str, order: WorkOrder, validators: Optional[List[str]] = None
) -> List[str]:
    """Validate the draft.

    Apply only the validators selected by the resolved content pack, including
    presentation-specific citation rules for research-backed content.

    Args:
        draft (str): The draft content to evaluate or transform.
        order (WorkOrder): The work order that defines the requested content run.
        validators (Optional[List[str]]): The validators value passed to validate draft.
            Defaults to ``None``.

    Returns:
        List[str]: The validated draft values in their documented order.
    """
    errors = _document_fence_errors(draft)
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
        if not isinstance(phrases, list):
            phrases = []
        for phrase in phrases:
            if str(phrase).lower() in lowered:
                errors.append("Banned phrase: {}".format(phrase))

    length = order.pack_options.get("length")
    if "word-count" in enabled and isinstance(length, str) and re.fullmatch(r"\d+:\d+", length):
        minimum, maximum = (int(item) for item in length.split(":"))
        if not minimum <= len(words) <= maximum:
            errors.append("Content must be between {} and {} words".format(minimum, maximum))
    if (
        "citation-integrity" in enabled
        and order.research_depth != ResearchDepth.NONE
        and not _has_required_citations(draft, order)
    ):
        style = str(order.pack_options.get("citation_style", "inline-links"))
        if style == "numbered-references":
            errors.append(
                "Research-backed drafts using numbered-references must include numbered "
                "in-text citations and a References section with source URLs"
            )
        else:
            errors.append("Research-backed drafts must include at least one source link")
    return errors


def _has_required_citations(draft: str, order: WorkOrder) -> bool:
    """Return whether a draft satisfies the configured citation presentation.

    Args:
        draft (str): Draft content whose citations are inspected.
        order (WorkOrder): Work order containing the citation-style option.

    Returns:
        bool: Whether the configured citation presentation is present.
    """
    style = str(order.pack_options.get("citation_style", "inline-links"))
    if style == "inline-links":
        return bool(re.search(r"https?://|]\(https?://", draft))
    if style == "numbered-references":
        heading = re.search(r"(?im)^#{1,6}\s+references\s*$", draft)
        body = draft[: heading.start()] if heading else draft
        references = draft[heading.end() :] if heading else ""
        has_marker = bool(re.search(r"\[(?:[1-9]\d*)\]", body))
        has_references = heading is not None
        has_url = bool(re.search(r"https?://", references))
        return has_marker and has_references and has_url
    return False


def validate_research_brief(brief: ResearchBrief) -> List[str]:
    """Validate the research brief.

    Args:
        brief (ResearchBrief): The research or content brief that defines the requested
            work.

    Returns:
        List[str]: The validated research brief values in their documented order.
    """
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
