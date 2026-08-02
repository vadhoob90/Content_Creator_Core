"""Perspective command-family entry point."""

from pathlib import Path
from typing import Any, Callable


def run(root: Path, args: Any, handler: Callable[[Path, Any], int]) -> int:
    """Execute one perspective subcommand."""
    return handler(root, args)
