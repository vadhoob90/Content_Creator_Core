"""Provide routing capabilities."""

from __future__ import annotations

from .domain import ResearchDepth, ResearchSource, RoutePlan, WorkOrder


class RoutingError(ValueError):
    """Report routing failures."""

    pass


def validate_work_order(order: WorkOrder) -> None:
    """Validate work order."""
    if order.research_depth == ResearchDepth.NONE and order.research_source != ResearchSource.NONE:
        raise RoutingError("No-research work cannot specify a research source")
    if order.research_depth != ResearchDepth.NONE and order.research_source == ResearchSource.NONE:
        raise RoutingError("Research work must specify supplied or agent research")
    if order.research_source == ResearchSource.SUPPLIED and not order.supplied_research_path:
        raise RoutingError("Supplied research requires supplied_research_path")


def build_route(order: WorkOrder) -> RoutePlan:
    """Build route."""
    validate_work_order(order)
    stages = []
    profiles = {}
    checkpoint = False

    if order.research_depth != ResearchDepth.NONE:
        stages.append("research")
        profiles["researcher"] = (
            "deep" if order.research_depth == ResearchDepth.DEEP else "balanced"
        )
        checkpoint = (
            order.research_depth == ResearchDepth.DEEP
            and order.research_source == ResearchSource.AGENT
        )
        if checkpoint:
            stages.append("research-approval")

    stages.extend(["draft", "validate", "critic", "quality-gate"])
    profiles["writer"] = "deep" if order.research_depth == ResearchDepth.DEEP else "balanced"
    profiles["critic"] = "deep" if order.research_depth == ResearchDepth.DEEP else "balanced"

    return RoutePlan(
        route="{}-{}-{}".format(
            order.format, order.research_depth.value, order.research_source.value
        ),
        stages=stages,
        requires_research_checkpoint=checkpoint,
        model_profiles=profiles,
    )
