"""Perspective command-family entry point."""

from pathlib import Path
from typing import Any


def run(root: Path, args: Any) -> int:
    """Execute one perspective subcommand."""
    from . import runtime

    return runtime._perspective_command(root, args)
