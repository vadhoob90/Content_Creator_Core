"""Demonstrate lifecycle stage composition without subclassing Core."""

from content_creator.domain import ResearchBrief, RunState
from content_creator.orchestrator import (
    CallableDraftReviewStage,
    CallableResearchStage,
    LifecycleStages,
)


def research(_state: RunState, supplied: ResearchBrief | None = None) -> ResearchBrief | None:
    """Return supplied research while retaining the Core checkpoint contract."""
    return supplied


def draft_review(state: RunState, _brief: ResearchBrief | None) -> RunState:
    """Return state after a host-owned draft-review callback."""
    return state


def main() -> None:
    """Construct the lifecycle stage collection used by ``Orchestrator``."""
    stages = LifecycleStages(
        research=CallableResearchStage(research),
        draft_review=CallableDraftReviewStage(draft_review),
    )
    print(type(stages.research).__name__, type(stages.draft_review).__name__)


if __name__ == "__main__":
    main()
