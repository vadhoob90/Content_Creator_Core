"""Resolve workspace-owned defaults on validated work orders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .domain import WorkOrder
from .packs import PackRegistry


def resolve_workspace_defaults(
    order: WorkOrder,
    coordinator_policy: Mapping[str, Any],
    packs: PackRegistry,
) -> WorkOrder:
    """Apply workspace defaults without overriding an explicit route selection.

    Args:
        order (WorkOrder): Validated work order to resolve in place.
        coordinator_policy (Mapping[str, Any]): Workspace coordinator configuration.
        packs (PackRegistry): Registry used to resolve the default pack's format.

    Returns:
        WorkOrder: The resolved work order.
    """
    default_voice = coordinator_policy.get("default_voice")
    if order.voice_id == "default" and default_voice:
        order.voice_id = str(default_voice)

    default_pack = str(coordinator_policy.get("default_pack") or "general-text")
    if (
        order.content_pack == "general-text"
        and order.format == "text"
        and default_pack != "general-text"
    ):
        pack = packs.get(default_pack)
        order.content_pack = pack.id
        order.format = pack.format
    return order
