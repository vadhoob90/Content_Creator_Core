"""Shared, side-effect-free command helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

PROVIDERS = ["anthropic", "openai", "codex-native", "claude-native"]


class AuthorHelpFormatter(argparse.HelpFormatter):
    """Hide suppressed subcommands without changing argparse behaviour."""

    def _format_action(self, action: argparse.Action) -> str:
        if isinstance(action, argparse._SubParsersAction):
            choices = action._choices_actions
            action._choices_actions = [item for item in choices if item.help != argparse.SUPPRESS]
            try:
                return super()._format_action(action)
            finally:
                action._choices_actions = choices
        return super()._format_action(action)


def resolve_root(value: Optional[str]) -> Path:
    return Path(value or ".").resolve()


def print_json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, default=str))
