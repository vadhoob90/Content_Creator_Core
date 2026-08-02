"""Perspective command-family entry point."""

from pathlib import Path
from typing import Any

from . import runtime


def run(root: Path, args: Any) -> int:
    """Execute one perspective subcommand."""
    return runtime._perspective_command(root, args)
