"""Provide intake capabilities."""

from __future__ import annotations

from typing import List, Optional

from .domain import (
    PlanningDecision,
    ResearchDepth,
    ResearchSource,
    WorkOrder,
)
from .runner import AgentRunner, AgentRunOptions


class ClarificationRequired(ValueError):
    """Represent a clarification required."""

    def __init__(self, questions: List[str]) -> None:
        """Initialize the clarification required."""
        self.questions = questions
        super().__init__("Clarification required: {}".format("; ".join(questions)))


class BriefingAgent:
    """Represent a briefing agent."""

    def __init__(self, runner: Optional[AgentRunner] = None):
        """Initialize the briefing agent."""
        self.runner = runner

    def plan(self, request: str, provider: Optional[str] = None) -> WorkOrder:
        """Plan briefing agent."""
        lowered = request.lower()
        content_format = "article" if "article" in lowered else "post"

        explicit_none = any(
            phrase in lowered for phrase in ("no research", "without research", "do not research")
        )
        explicit_deep = any(
            phrase in lowered
            for phrase in ("deep research", "deeply research", "comprehensive research")
        )
        explicit_light = "research" in lowered and not explicit_none and not explicit_deep

        if explicit_none:
            depth = ResearchDepth.NONE
            source = ResearchSource.NONE
        elif explicit_deep:
            depth = ResearchDepth.DEEP
            source = ResearchSource.AGENT
        elif explicit_light:
            depth = ResearchDepth.LIGHT
            source = ResearchSource.AGENT
        elif self.runner:
            decision = self.runner.run(
                role="briefing-agent",
                role_key="briefing-agent",
                instruction=(
                    "Turn this request into a work order. Choose the least research needed. "
                    "Use agent research when research is needed."
                ),
                payload={"request": request},
                options=AgentRunOptions(output_model=PlanningDecision, provider=provider),
            )
            if decision.needs_clarification or not decision.work_order:
                raise ClarificationRequired(
                    decision.clarification_questions
                    or ["Please clarify the intended format and research depth."]
                )
            decision.work_order.provider = provider
            return decision.work_order
        else:
            depth = ResearchDepth.NONE
            source = ResearchSource.NONE

        return WorkOrder(
            request=request,
            topic=request,
            content_pack=("linkedin-article" if content_format == "article" else "linkedin-post"),
            format=content_format,
            research_depth=depth,
            research_source=source,
            provider=provider,
        )


# Compatibility alias for callers migrating from LinkedIn Writer.
IntakePlanner = BriefingAgent
