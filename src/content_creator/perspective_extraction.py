"""Extract reusable perspective proposals after publication."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .domain import RunEvent, RunState
from .perspectives import PerspectiveExtraction, PerspectiveProposalStore
from .runner import AgentRunOptions


@dataclass(frozen=True)
class PerspectiveExtractionServices:
    """Collect collaborators used during perspective extraction."""

    root: Path
    configuration: Any
    store: Any
    runner: Any


def extract_perspectives(
    root: Path,
    configuration: Any,
    store: Any,
    runner: Any,
    state: RunState,
    draft: str,
    assessment: Dict[str, Any],
) -> None:
    """Extract reusable proposals for each selected perspective.

    Args:
        root (Path): The workspace root directory.
        configuration (Any): Validated runtime configuration.
        store (Any): Persisted run store.
        runner (Any): Normalized agent runner.
        state (RunState): Published run state.
        draft (str): Exact published draft.
        assessment (Dict[str, Any]): Publication assessment evidence.

    Returns:
        None: Candidate proposals and events are persisted in place.
    """
    services = PerspectiveExtractionServices(root, configuration, store, runner)
    for selection in state.work_order.perspective_selections:
        try:
            _extract_perspective(services, state, selection, draft, assessment)
        except Exception as exc:
            state.events.append(RunEvent(name="perspective_update_failed", detail=str(exc)))


def _extract_perspective(
    services: PerspectiveExtractionServices,
    state: RunState,
    selection: Any,
    draft: str,
    assessment: Dict[str, Any],
) -> None:
    """Extract and stage one context-scoped perspective proposal.

    Build a context-pinned request, retain optional research evidence, persist the
    normalized extraction, and stage candidates without activating them.

    Args:
        services (PerspectiveExtractionServices): Collaborators used for extraction.
        state (RunState): Published run state.
        selection (Any): Resolved perspective selection.
        draft (str): Exact published draft.
        assessment (Dict[str, Any]): Publication assessment evidence.

    Returns:
        None: The proposal and audit event are persisted in place.
    """
    order = state.work_order
    extraction_order = order.model_copy(deep=True)
    extraction_order.perspective_context = selection.context_id
    extraction_order.perspective_version = selection.version
    extraction_order.perspective_selections = [selection]
    instruction = (
        "Propose only reusable author positions evidenced by this published run. "
        "Preserve qualifications and keep every proposal in the explicitly resolved "
        "context. Compare direct author input and explicit feedback with active entries. "
        "When they conflict, use qualify, replace, or supersede and name the exact target "
        "entry id. Never activate a proposal. Conflict policy: {}."
    ).format(services.configuration.perspective_policy.get("conflict_policy", "propose-update"))
    research_path = services.store.run_dir(state.id) / "research.json"
    extraction = services.runner.run(
        role="perspective-extractor",
        role_key="perspective-extractor",
        instruction=instruction,
        payload={
            "work_order": order.model_dump(mode="json"),
            "draft": draft,
            "assessment": assessment,
            "research": (
                json.loads(services.store.read_artifact(state.id, "research.json"))
                if research_path.exists()
                else None
            ),
        },
        options=AgentRunOptions(
            order=extraction_order,
            output_model=PerspectiveExtraction,
            provider=order.provider,
        ),
    )
    filename = (
        "perspective-extraction.json"
        if len(order.perspective_selections) == 1
        else f"perspective-extraction-{selection.context_id}.json"
    )
    services.store.write_artifact(state.id, filename, extraction)
    paths = PerspectiveProposalStore(services.root, order.voice_id, selection.context_id).apply(
        state.id, extraction
    )
    state.events.append(
        RunEvent(name="perspective_candidates_proposed", detail=f"count={len(paths)}")
    )
