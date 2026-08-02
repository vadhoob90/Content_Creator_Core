"""Voice command-family entry point."""

from pathlib import Path
from typing import Any, Callable


def run(root: Path, args: Any, handler: Callable[[Path, Any], int]) -> int:
    """Execute one voice subcommand."""
    return handler(root, args)
