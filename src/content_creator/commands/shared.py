"""Implement the shared command family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

PROVIDERS = ["anthropic", "bedrock", "openai", "codex-native", "claude-native"]
ADVANCED_HELP = (
    "Advanced commands:\n"
    "  init, agents, provider, plan, coordinator (including next-actions),\n"
    "  pack, packs, voice, perspective, approve-research, reject-research, eval\n\n"
    "Use: content-creator <command> --help"
)


class AuthorHelpFormatter(argparse.HelpFormatter):
    """Hide suppressed subcommands without changing argparse behaviour."""

    def _format_action(self, action: argparse.Action) -> str:
        """Format the action.

        Args:
            action (argparse.Action): The action value passed to format action.

        Returns:
            str: The formatted text for action.
        """
        if isinstance(action, argparse._SubParsersAction):
            choices = action._choices_actions
            action._choices_actions = [item for item in choices if item.help != argparse.SUPPRESS]
            try:
                return super()._format_action(action)
            finally:
                action._choices_actions = choices
        return super()._format_action(action)


def resolve_root(value: Optional[str]) -> Path:
    """Resolve the root.

    Args:
        value (Optional[str]): The value to process.

    Returns:
        Path: The resolved filesystem path for root.
    """
    return Path(value or ".").resolve()


def print_json(value: Any) -> None:
    """Return the print json.

    Args:
        value (Any): The value to process.

    Returns:
        None: The callable updates print json state and returns no value.
    """
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, default=str))
