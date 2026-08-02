"""Voice command-family entry point."""

from pathlib import Path
from typing import Any


def run(root: Path, args: Any) -> int:
    """Execute one voice subcommand."""
    from . import runtime

    return runtime._voice_command(root, args)
