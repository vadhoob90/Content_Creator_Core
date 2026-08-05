"""Provide stages contracts and behavior."""

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
        """Execute the research stage workflow.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            supplied_brief (Optional[ResearchBrief]): The supplied brief value passed to
                execute. Defaults to ``None``.

        Returns:
            Optional[ResearchBrief]: The resulting execute when available; otherwise
                ``None``.

        Raises:
            NotImplementedError: If the not implemented operation cannot complete.
        """
        raise NotImplementedError


class DraftReviewStage(Protocol):
    """Represent a draft review stage."""

    def execute(self, state: RunState, brief: Optional[ResearchBrief]) -> RunState:
        """Execute the draft review stage workflow.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            brief (Optional[ResearchBrief]): The research or content brief that defines the
                requested work.

        Returns:
            RunState: The resulting run state for execute.

        Raises:
            NotImplementedError: If the not implemented operation cannot complete.
        """
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
        """Execute the callable research stage workflow.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            supplied_brief (Optional[ResearchBrief]): The supplied brief value passed to
                execute. Defaults to ``None``.

        Returns:
            Optional[ResearchBrief]: The resulting execute when available; otherwise
                ``None``.
        """
        return self.handler(state, supplied_brief)


@dataclass(frozen=True)
class CallableDraftReviewStage:
    """Represent a callable draft review stage."""

    handler: Callable[[RunState, Optional[ResearchBrief]], RunState]

    def execute(self, state: RunState, brief: Optional[ResearchBrief]) -> RunState:
        """Execute callable draft review stage.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            brief (Optional[ResearchBrief]): The research or content brief that defines the
                requested work.

        Returns:
            RunState: The resulting run state for execute.
        """
        return self.handler(state, brief)


@dataclass(frozen=True)
class LifecycleStages:
    """Represent the lifecycle stages contract."""

    research: ResearchStage
    draft_review: DraftReviewStage
