"""Render concise human-readable voice status output."""

from __future__ import annotations

from typing import Any


def render_voice_status(result: dict[str, Any]) -> str:
    """Render lifecycle state without exposing hashes or storage internals.

    Args:
        result (dict[str, Any]): Existing stable machine-readable status result.

    Returns:
        str: Concise author-facing status and next action.
    """
    onboarding = result.get("onboarding") or {}
    active = result.get("active") or {}
    lines = ["Writing style status"]
    if onboarding.get("status") == "undecided":
        lines.extend(
            [
                "Status: choose how to begin",
                "Neutral starter: content-creator setup starter",
                "Personalised from my writing: content-creator setup source-derived",
            ]
        )
        return "\n".join(lines)
    if active.get("status") == "active":
        strategy = str(active.get("strategy", "source-derived"))
        kind = "neutral starter" if strategy.startswith("starter") else "personalised"
        lines.extend(
            [
                f"Status: ready ({kind})",
                f"Version: {active.get('active_version', 'available')}",
                'Next: content-creator start "<request>"',
            ]
        )
        return "\n".join(lines)
    if result.get("candidate"):
        lines.extend(
            [
                "Status: review required",
                "Next: content-creator personalisation show",
            ]
        )
        return "\n".join(lines)
    lines.extend(["Status: setup in progress", "Next: content-creator setup"])
    return "\n".join(lines)
