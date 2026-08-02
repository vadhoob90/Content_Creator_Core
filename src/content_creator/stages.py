"""Composable application-stage contracts for the Core run lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .domain import ResearchBrief, RunState


class ResearchStage(Protocol):
    def execute(
        self,
        state: RunState,
        supplied_brief: Optional[ResearchBrief] = None,
    ) -> Optional[ResearchBrief]:
        raise NotImplementedError


class DraftReviewStage(Protocol):
    def execute(self, state: RunState, brief: Optional[ResearchBrief]) -> RunState:
        raise NotImplementedError


@dataclass(frozen=True)
class CallableResearchStage:
    handler: Callable[[RunState, Optional[ResearchBrief]], Optional[ResearchBrief]]

    def execute(
        self,
        state: RunState,
        supplied_brief: Optional[ResearchBrief] = None,
    ) -> Optional[ResearchBrief]:
        return self.handler(state, supplied_brief)


@dataclass(frozen=True)
class CallableDraftReviewStage:
    handler: Callable[[RunState, Optional[ResearchBrief]], RunState]

    def execute(self, state: RunState, brief: Optional[ResearchBrief]) -> RunState:
        return self.handler(state, brief)


@dataclass(frozen=True)
class LifecycleStages:
    """Replaceable application stages composed by :class:`Orchestrator`."""

    research: ResearchStage
    draft_review: DraftReviewStage
