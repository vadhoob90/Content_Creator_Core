"""Stable command-line façade for Content Creator Core.

Keep this module small: console scripts and consumers import ``main`` and
``build_parser`` from here. Implementations belong to ``content_creator.commands``.
"""

from __future__ import annotations

from typing import Any

from .commands import runtime
from .orchestrator import Orchestrator


def build_parser():
    """Build the backwards-compatible top-level argument parser."""
    return runtime.build_parser()


def _sync_overrides() -> None:
    """Preserve the documented/tested ability to replace CLI dependencies."""
    runtime.Orchestrator = Orchestrator


def _main(argv: Any = None) -> int:
    _sync_overrides()
    return runtime._main(argv)


def main(argv: Any = None) -> int:
    _sync_overrides()
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
