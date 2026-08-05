"""Provide CLI contracts and behavior.

Keep this module small: console scripts and consumers import ``main`` and
``build_parser`` from here. Implementations belong to ``content_creator.commands``.
"""

from __future__ import annotations

from typing import Any

from .commands import runtime
from .orchestrator import Orchestrator


def build_parser() -> Any:
    """Build the backwards-compatible top-level argument parser.

    Returns:
        Any: The constructed value for parser.
    """
    return runtime.build_parser()


def _sync_overrides() -> None:
    """Preserve the documented/tested ability to replace CLI dependencies.

    Returns:
        None: The callable updates sync overrides state and returns no value.
    """
    setattr(runtime, "Orchestrator", Orchestrator)  # noqa: B010


def _main(argv: Any = None) -> int:
    """Run the internal command-line entry point.

    Args:
        argv (Any): The command-line argument sequence. Defaults to ``None``.

    Returns:
        int: The resulting numeric value for main.
    """
    _sync_overrides()
    return runtime._main(argv)


def main(argv: Any = None) -> int:
    """Run the public command-line entry point.

    Args:
        argv (Any): The command-line argument sequence. Defaults to ``None``.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    _sync_overrides()
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
