"""Apply explicit visual insertion anchors without changing author prose."""

import posixpath
import re
from typing import Any

from .draft_bundles.markdown import _mask_code
from .visual_contracts import VisualError


def place_visuals(content: str, source: str, placements: list[dict[str, Any]]) -> str:
    """Apply each explicit placement marker exactly once.

    Args:
        content (str): Governed Markdown before export mapping.
        source (str): Workspace-relative text artifact path.
        placements (list[dict[str, Any]]): Ordered source, anchor, and alt-text descriptions.

    Returns:
        str: Markdown with explicit placement markers replaced by image links.

    Raises:
        VisualError: If an anchor is missing, ambiguous, malformed, or unresolved.
    """
    result = content
    used = set()
    for placement in placements:
        anchor = placement.get("anchor")
        if not anchor:
            continue
        if not re.fullmatch(r"<!-- visual:[a-z0-9]+(?:-[a-z0-9]+)* -->", anchor):
            raise VisualError("Use an explicit <!-- visual:slot-id --> insertion anchor")
        visible = _mask_code(result)
        if anchor in used or visible.count(anchor) != 1:
            raise VisualError(f"Missing or ambiguous visual anchor: {anchor}")
        used.add(anchor)
        relative = posixpath.relpath(placement["source_path"], posixpath.dirname(source))
        alt = re.sub(r"([\\\[\]])", r"\\\1", " ".join(placement["alt_text"].splitlines()))
        start = visible.index(anchor)
        result = result[:start] + f"![{alt}](<{relative}>)" + result[start + len(anchor) :]
    if "<!-- visual:" in _mask_code(result):
        raise VisualError("Markdown contains an unresolved visual placement anchor")
    return result
