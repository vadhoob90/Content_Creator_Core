"""Provide expected runtime instruction composition without invoking a model."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .configuration import Configuration
from .domain import PerspectiveSelection, ResearchDepth, ResearchSource, WorkOrder
from .packs import PackRegistry
from .prompting import PromptAssembler


def explain_context(
    root: Path,
    role: str,
    voice_id: Optional[str] = None,
    pack_id: Optional[str] = None,
    research: str = "none",
    perspectives: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Return a read-only composition forecast for one agent role.

    Args:
        root (Path): Workspace root directory.
        role (str): Repository-owned agent role.
        voice_id (Optional[str]): Voice selection override. Defaults to ``None``.
        pack_id (Optional[str]): Content-pack override. Defaults to ``None``.
        research (str): Expected research depth. Defaults to ``"none"``.
        perspectives (Optional[list[str]]): Explicit perspective contexts. Defaults to
            ``None``.

    Returns:
        dict[str, Any]: Resolved forecast and privacy-safe ordered source decisions.
    """
    policy = Configuration(root).coordinator_policy
    selected_voice = voice_id or policy.get("default_voice") or "default"
    selected_pack = pack_id or str(policy["default_pack"])
    pack = PackRegistry(root).resolve(selected_pack)
    depth = ResearchDepth(research)
    selections = [PerspectiveSelection(context_id=context_id) for context_id in perspectives or []]
    order = WorkOrder(
        request="Runtime context preflight",
        topic="Runtime context preflight",
        voice_id=selected_voice,
        content_pack=selected_pack,
        format=pack.format,
        research_depth=depth,
        research_source=(
            ResearchSource.NONE if depth == ResearchDepth.NONE else ResearchSource.AGENT
        ),
        perspective_selections=selections,
    )
    composition = PromptAssembler(root).compose(role, order)
    return {
        "mode": "preflight",
        "role": role,
        "voice": selected_voice,
        "pack": selected_pack,
        "research": depth.value,
        "perspectives": [item.context_id for item in selections],
        "instruction_layers": [layer.model_dump(mode="json") for layer in composition.layers],
    }
