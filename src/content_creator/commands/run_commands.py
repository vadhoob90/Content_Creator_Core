"""Construct and submit work orders for the run command."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..configuration import Configuration
from ..domain import (
    AuthorContribution,
    PerspectiveMode,
    PerspectiveSelection,
    ResearchDepth,
    ResearchSource,
    WorkOrder,
)
from ..intake import ClarificationRequired
from ..packs import PackRegistry
from ..work_order_resolution import resolve_workspace_defaults
from .context import CommandContext


def _brief_order(context: CommandContext) -> WorkOrder:
    """Return the brief order.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        WorkOrder: The resulting work order for brief order.
    """
    arguments = context.arguments
    brief_fields = yaml.safe_load(Path(arguments.brief).read_text(encoding="utf-8"))
    research = brief_fields.pop("research", {}) or {}
    brief_fields.setdefault("research_depth", research.get("depth", "none"))
    brief_fields.setdefault("research_source", research.get("source", "none"))
    order = WorkOrder.model_validate(brief_fields)
    order.provider = arguments.provider or order.provider
    order.voice_id = arguments.voice or order.voice_id
    order.voice_version = arguments.voice_version or order.voice_version
    return order


def _explicit_order(context: CommandContext) -> WorkOrder:
    """Return the explicit order.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        WorkOrder: The resulting work order for explicit order.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    arguments = context.arguments
    if not arguments.request:
        raise ValueError("run requires a request or --brief")
    content_format = arguments.format
    if arguments.pack:
        content_format = PackRegistry(context.root).get(arguments.pack).format
    depth = ResearchDepth(arguments.research or "none")
    source = ResearchSource(
        arguments.research_source or ("none" if depth == ResearchDepth.NONE else "agent")
    )
    pack_options = {
        key: option
        for key, option in {
            "length": arguments.length,
            "language": arguments.language,
            "structure": arguments.structure,
            "destination": arguments.destination,
            "citation_style": arguments.citation_style,
        }.items()
        if option is not None
    }
    return WorkOrder(
        request=arguments.request,
        topic=arguments.topic or arguments.request,
        content_pack=arguments.pack or "general-text",
        voice_id=arguments.voice or "default",
        voice_version=arguments.voice_version,
        format=content_format or "text",
        research_depth=depth,
        research_source=source,
        supplied_research_path=arguments.research_file,
        provider=arguments.provider,
        objective=arguments.objective or "share a useful perspective",
        audience=arguments.audience or "professional audience",
        pack_options=pack_options,
    )


def _planned_order(context: CommandContext) -> WorkOrder | None:
    """Return the planned order.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        WorkOrder | None: The resulting planned order when available; otherwise
            ``None``.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    arguments = context.arguments
    if not arguments.request:
        raise ValueError("run requires a request or --brief")
    try:
        order = context.orchestrator.plan_request(arguments.request, provider=arguments.provider)
    except ClarificationRequired as error:
        context.emit({"needs_clarification": True, "questions": error.questions})
        return None
    if arguments.voice:
        order.voice_id = arguments.voice
    if arguments.voice_version:
        order.voice_version = arguments.voice_version
    return order


def _build_order(context: CommandContext) -> WorkOrder | None:
    """Build the order.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        WorkOrder | None: The constructed order when available; otherwise ``None``.
    """
    arguments = context.arguments
    order: WorkOrder | None
    if arguments.brief:
        order = _brief_order(context)
    elif arguments.pack or arguments.format or arguments.research or arguments.research_source:
        order = _explicit_order(context)
    else:
        order = _planned_order(context)
    if order is None:
        return None
    return resolve_workspace_defaults(
        order,
        Configuration(context.root).coordinator_policy,
        PackRegistry(context.root),
    )


def _apply_perspective(order: WorkOrder, context: CommandContext) -> None:
    """Apply the perspective.

    Args:
        order (WorkOrder): The work order that defines the requested content run.
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        None: The callable updates apply perspective state and returns no value.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    arguments = context.arguments
    if arguments.no_perspective:
        order.perspective_mode = PerspectiveMode.DISABLED
        order.perspective_context = None
        order.perspective_version = None
        order.perspective_selections = []
        return
    if arguments.perspective_context:
        order.perspective_selections = [
            PerspectiveSelection(
                context_id=context_id,
                version=(
                    arguments.perspective_version
                    if index == 0 and len(arguments.perspective_context) == 1
                    else None
                ),
            )
            for index, context_id in enumerate(arguments.perspective_context)
        ]
        order.perspective_context = order.perspective_selections[0].context_id
    if arguments.perspective_version:
        if len(arguments.perspective_context) != 1:
            raise ValueError("--perspective-version requires exactly one --perspective-context")
        order.perspective_version = arguments.perspective_version


def _apply_contribution(order: WorkOrder, context: CommandContext) -> None:
    """Apply the contribution.

    Args:
        order (WorkOrder): The work order that defines the requested content run.
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        None: The callable updates apply contribution state and returns no value.
    """
    arguments = context.arguments
    if not any(
        (
            arguments.thesis,
            arguments.intended_challenge,
            arguments.personal_basis,
            arguments.perspective_entry,
        )
    ):
        return
    order.author_contribution = AuthorContribution(
        thesis=arguments.thesis,
        intended_challenge=arguments.intended_challenge,
        personal_basis=arguments.personal_basis,
        supplied_by_author=arguments.author_supplied,
        reusable_perspective_entry_ids=arguments.perspective_entry,
        provenance_notes=["Supplied through the run command"],
    )


def _apply_lineage(order: WorkOrder, context: CommandContext) -> None:
    """Apply the lineage.

    Args:
        order (WorkOrder): The work order that defines the requested content run.
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        None: The callable updates apply lineage state and returns no value.
    """
    arguments = context.arguments
    if arguments.parent_run:
        parent = context.orchestrator.store.load(arguments.parent_run)
        order.parent_run_id = parent.id
        order.content_session_id = parent.work_order.content_session_id
    elif arguments.content_session:
        order.content_session_id = arguments.content_session


def run(context: CommandContext) -> int:
    """Run the run commands workflow.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    if context.arguments.show_context:
        context.orchestrator.runner.enable_context_trace()
    order = _build_order(context)
    if order is None:
        return 3
    _apply_perspective(order, context)
    _apply_contribution(order, context)
    _apply_lineage(order, context)
    if context.arguments.idempotency_key is None:
        state = context.orchestrator.start(order)
    else:
        state = context.orchestrator.start(
            order,
            idempotency_key=context.arguments.idempotency_key,
        )
    context.emit(state)
    return 0
