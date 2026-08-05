"""Composable application-stage contracts for the Core run lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .domain import ResearchBrief, RunState


class ResearchStage(Protocol):
    """Represent a research stage."""

    def execute(
        self,
        state: RunState,
        supplied_brief: Optional[ResearchBrief] = None,
    ) -> Optional[ResearchBrief]:
        """Execute research stage."""
        raise NotImplementedError


class DraftReviewStage(Protocol):
    """Represent a draft review stage."""

    def execute(self, state: RunState, brief: Optional[ResearchBrief]) -> RunState:
        """Execute draft review stage."""
        raise NotImplementedError


@dataclass(frozen=True)
class CallableResearchStage:
    """Represent a callable research stage."""

    handler: Callable[[RunState, Optional[ResearchBrief]], Optional[ResearchBrief]]

    def execute(
        self,
        state: RunState,
        supplied_brief: Optional[ResearchBrief] = None,
    ) -> Optional[ResearchBrief]:
        """Execute callable research stage."""
        return self.handler(state, supplied_brief)


@dataclass(frozen=True)
class CallableDraftReviewStage:
    """Represent a callable draft review stage."""

    handler: Callable[[RunState, Optional[ResearchBrief]], RunState]

    def execute(self, state: RunState, brief: Optional[ResearchBrief]) -> RunState:
        """Execute callable draft review stage."""
        return self.handler(state, brief)


@dataclass(frozen=True)
class LifecycleStages:
    """Replaceable application stages composed by :class:`Orchestrator`."""

    research: ResearchStage
    draft_review: DraftReviewStage
