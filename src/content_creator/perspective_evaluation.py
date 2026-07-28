from __future__ import annotations

import json
import re
from pathlib import Path

from .domain import WorkOrder
from .perspectives import PerspectiveEntryStatus, PerspectiveRegistry

_POSITION_MARKER = re.compile(
    r"\b(?:I believe|I think|my view is|in my view|I recommend|I prefer)\b",
    re.I,
)


def evaluate_perspective_output(root: Path, order: WorkOrder, draft: str) -> dict:
    errors = []
    markers = _POSITION_MARKER.findall(draft)
    resolved = None
    active_entries = []
    if order.perspective_context:
        resolved = PerspectiveRegistry(root, order.voice_id).resolve(
            order.perspective_context,
            order.perspective_version,
            allow_inactive=order.resolved_perspective,
        )
        entries = json.loads(
            (root / resolved["path"] / "entries.json").read_text(encoding="utf-8")
        )
        active_entries = [
            item
            for item in entries
            if item.get("status") == PerspectiveEntryStatus.APPROVED.value
        ]

    contribution = order.author_contribution
    request_supplies_position = bool(_POSITION_MARKER.search(order.request))
    contribution_supplies_position = bool(
        contribution
        and (
            contribution.thesis
            or contribution.intended_challenge
            or contribution.personal_basis
        )
        and contribution.supplied_by_author
    )
    if (
        markers
        and not active_entries
        and not request_supplies_position
        and not contribution_supplies_position
    ):
        errors.append("Draft presents an unsupported author perspective")

    requested_ids = (
        contribution.reusable_perspective_entry_ids if contribution else []
    )
    active_ids = {item["id"] for item in active_entries}
    unknown_ids = sorted(set(requested_ids) - active_ids)
    if unknown_ids:
        errors.append(
            "Author contribution references unavailable perspective entries: {}".format(
                ", ".join(unknown_ids)
            )
        )
    return {
        "passed": not errors,
        "errors": errors,
        "position_markers": markers,
        "perspective": resolved,
        "selected_entry_ids": requested_ids,
    }
