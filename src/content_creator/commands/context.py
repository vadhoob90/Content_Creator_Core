"""Typed dependencies shared by focused command handlers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..orchestrator import Orchestrator


@dataclass
class CommandContext:
    """Resolved command inputs and lazily constructed application dependencies."""

    root: Path
    arguments: argparse.Namespace
    emit: Callable[[Any], None]
    orchestrator_type: type[Orchestrator]
    _orchestrator: Orchestrator | None = field(default=None, init=False)

    @property
    def orchestrator(self) -> Orchestrator:
        """Return one orchestrator instance for commands that require it."""
        if self._orchestrator is None:
            self._orchestrator = self.orchestrator_type(self.root)
        return self._orchestrator
