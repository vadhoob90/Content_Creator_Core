"""Implement the context command family."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..orchestrator import Orchestrator


@dataclass
class CommandContext:
    """Represent the command context contract."""

    root: Path
    arguments: argparse.Namespace
    emit: Callable[[Any], None]
    orchestrator_type: type[Orchestrator]
    _orchestrator: Orchestrator | None = field(default=None, init=False)

    @property
    def orchestrator(self) -> Orchestrator:
        """Return one orchestrator instance for commands that require it.

        Returns:
            Orchestrator: The resulting orchestrator for orchestrator.
        """
        if self._orchestrator is None:
            self._orchestrator = self.orchestrator_type(self.root)
        return self._orchestrator
