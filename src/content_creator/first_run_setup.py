"""Provide the calm first-run author journey."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .configuration import Configuration
from .coordinator_models import (
    CoordinatorAction,
    FirstRunSetup,
    SetupMilestone,
    WorkspaceSnapshot,
)
from .provider_setup import provider_choices
from .voice_assessment import save_score_preference
from .voice_builder import VoiceBuilder
from .voice_models import (
    Authorisation,
    VoiceOnboardingRecord,
    VoiceStrategy,
    VoiceWorkOrder,
    save_voice_onboarding,
)
from .voices import VoiceRegistry, load_voice_onboarding


def build_first_run_setup(snapshot: WorkspaceSnapshot) -> FirstRunSetup:
    """Build four author milestones from the authoritative workspace snapshot.

    Args:
        snapshot (WorkspaceSnapshot): Persisted coordinator state to project.

    Returns:
        FirstRunSetup: A progressive, author-facing setup view.
    """
    milestones = [
        _workspace_milestone(snapshot),
        _writing_style_milestone(snapshot),
        _provider_milestone(snapshot),
        _first_piece_milestone(snapshot),
    ]
    complete_states = {"ready", "reviewable", "complete"}
    return FirstRunSetup(
        completed_count=sum(item.status in complete_states for item in milestones),
        ready_for_content=_ready_for_content(snapshot),
        milestones=milestones,
        recommended_action=snapshot.recommended_action,
        choices=_setup_choices(snapshot),
    )


def activate_setup_writing_style(root: Path, strategy: str) -> dict[str, Any]:
    """Apply an explicit first-run writing-style choice using known workspace data.

    Args:
        root (Path): Author workspace root.
        strategy (str): Either ``starter`` or ``source-derived``.

    Returns:
        dict[str, Any]: Concise activation or source-collection result.

    Raises:
        ValueError: If no undecided generated voice exists or strategy is invalid.
    """
    if strategy not in {"starter", "source-derived"}:
        raise ValueError("Writing style must be starter or source-derived")
    onboarding = _undecided_onboarding(root)
    intended_uses = _workspace_content_packs(root)
    if strategy == "starter":
        return _activate_starter(root, onboarding, intended_uses)
    return _begin_source_derived(root, onboarding, intended_uses)


def _workspace_milestone(snapshot: WorkspaceSnapshot) -> SetupMilestone:
    """Return the workspace milestone.

    Args:
        snapshot (WorkspaceSnapshot): Persisted coordinator state to project.

    Returns:
        SetupMilestone: Workspace readiness milestone.
    """
    ready = snapshot.is_workspace and snapshot.health.get("status") == "ok"
    return SetupMilestone(
        id="workspace",
        label="Workspace",
        status="ready" if ready else "attention-required",
        summary="Ready" if ready else "Run workspace creation or doctor checks",
    )


def _writing_style_milestone(snapshot: WorkspaceSnapshot) -> SetupMilestone:
    """Return the writing-style milestone.

    Args:
        snapshot (WorkspaceSnapshot): Persisted coordinator state to project.

    Returns:
        SetupMilestone: Writing-style readiness milestone.
    """
    active = next((voice for voice in snapshot.voices if voice.active_status == "active"), None)
    if active:
        kind = "Neutral starter" if str(active.strategy).startswith("starter") else "Personalised"
        return _milestone("writing-style", "Writing style", "ready", f"{kind} ready")
    undecided = next(
        (voice for voice in snapshot.voices if voice.onboarding_status == "undecided"), None
    )
    if undecided:
        return _milestone(
            "writing-style", "Writing style", "choice-required", "Choose how to begin"
        )
    candidate = next(
        (voice for voice in snapshot.voices if voice.candidate_decision == "pending"), None
    )
    if candidate:
        return _milestone(
            "writing-style", "Writing style", "review-required", "Review personalised style"
        )
    return _milestone("writing-style", "Writing style", "in-progress", "Finish personalised setup")


def _provider_milestone(snapshot: WorkspaceSnapshot) -> SetupMilestone:
    """Return the model-connection milestone.

    Args:
        snapshot (WorkspaceSnapshot): Persisted coordinator state to project.

    Returns:
        SetupMilestone: Provider readiness milestone.
    """
    provider = snapshot.provider_status
    if provider.status == "verified":
        return _milestone(
            "model-connection", "Model connection", "ready", f"{provider.name} verified"
        )
    if provider.name:
        return _milestone(
            "model-connection",
            "Model connection",
            "verification-required",
            f"Verify {provider.name}",
        )
    return _milestone(
        "model-connection", "Model connection", "choice-required", "Choose and verify a model"
    )


def _first_piece_milestone(snapshot: WorkspaceSnapshot) -> SetupMilestone:
    """Return the first-piece milestone.

    Args:
        snapshot (WorkspaceSnapshot): Persisted coordinator state to project.

    Returns:
        SetupMilestone: First content milestone.
    """
    run = next((item for item in snapshot.runs if item.authoritative), None)
    if run and run.status == "published":
        return _milestone("first-piece", "First piece", "complete", "Approved copy saved")
    if run and run.status in {"ready", "needs_author"}:
        return _milestone("first-piece", "First piece", "reviewable", "Ready for review")
    if run:
        return _milestone("first-piece", "First piece", "in-progress", "Creation in progress")
    if _ready_for_content(snapshot):
        return _milestone("first-piece", "First piece", "available", "Tell me what to create")
    return _milestone("first-piece", "First piece", "blocked", "Complete setup first")


def _ready_for_content(snapshot: WorkspaceSnapshot) -> bool:
    """Return whether content execution prerequisites are ready.

    Args:
        snapshot (WorkspaceSnapshot): Persisted coordinator state to evaluate.

    Returns:
        bool: Whether an active voice and verified provider are available.
    """
    return bool(snapshot.active_voice_ids) and snapshot.provider_status.status == "verified"


def _milestone(identifier: str, label: str, status: str, summary: str) -> SetupMilestone:
    """Create one milestone with explicit named fields.

    Args:
        identifier (str): Stable milestone identifier.
        label (str): Author-facing milestone label.
        status (str): Derived milestone state.
        summary (str): Concise author-facing explanation.

    Returns:
        SetupMilestone: Validated milestone.
    """
    return SetupMilestone(id=identifier, label=label, status=status, summary=summary)


def _setup_choices(snapshot: WorkspaceSnapshot) -> list[CoordinatorAction]:
    """Return choices relevant to the current setup checkpoint.

    Args:
        snapshot (WorkspaceSnapshot): Persisted coordinator state to evaluate.

    Returns:
        list[CoordinatorAction]: Explicit choices for the current checkpoint.
    """
    if any(voice.onboarding_status == "undecided" for voice in snapshot.voices):
        return [
            CoordinatorAction(
                id="use-starter",
                label="Neutral starter",
                command=["setup", "starter"],
                mutates_workspace=True,
                requires_confirmation=True,
            ),
            CoordinatorAction(
                id="use-my-writing",
                label="Personalised from my writing",
                command=["setup", "source-derived"],
                mutates_workspace=True,
                requires_confirmation=True,
            ),
        ]
    if snapshot.active_voice_ids and snapshot.provider_status.status != "verified":
        return provider_choices()
    return []


def _undecided_onboarding(root: Path) -> VoiceOnboardingRecord:
    """Return the configured undecided voice record.

    Args:
        root (Path): Author workspace root.

    Returns:
        VoiceOnboardingRecord: Voice whose route needs an explicit choice.

    Raises:
        ValueError: If the workspace has no undecided voice.
    """
    preferred = Configuration(root).coordinator_policy.get("default_voice")
    if preferred:
        record = load_voice_onboarding(root, str(preferred))
        if record and record.status == "undecided":
            return record
    for path in sorted((root / "profiles").glob("*/onboarding.json")):
        record = load_voice_onboarding(root, path.parent.name)
        if record and record.status == "undecided":
            return record
    raise ValueError("No undecided writing style is available in this workspace")


def _workspace_content_packs(root: Path) -> list[str]:
    """Return packs enabled by generated publication destinations.

    Args:
        root (Path): Author workspace root.

    Returns:
        list[str]: Enabled content-pack identifiers.
    """
    packs = sorted(
        path.parent.name for path in (root / "content").glob("*/published") if path.is_dir()
    )
    return packs or [str(Configuration(root).coordinator_policy["default_pack"])]


def _activate_starter(
    root: Path,
    onboarding: VoiceOnboardingRecord,
    intended_uses: list[str],
) -> dict[str, Any]:
    """Activate the neutral starter from known setup state.

    Args:
        root (Path): Author workspace root.
        onboarding (VoiceOnboardingRecord): Generated undecided voice record.
        intended_uses (list[str]): Enabled content packs.

    Returns:
        dict[str, Any]: Concise activation result.
    """
    VoiceRegistry(root).activate_starter(
        voice_id=onboarding.voice_id,
        display_name=onboarding.display_name,
        author_name=onboarding.author_name,
        selected_by=onboarding.author_name,
        intended_uses=intended_uses,
    )
    save_score_preference(
        root,
        onboarding.voice_id,
        enabled=False,
        method="deterministic",
        selected_by=onboarding.author_name,
    )
    return {
        "status": "writing-style-ready",
        "strategy": "starter",
        "author_name": onboarding.author_name,
        "next_step": "Connect and verify a model provider.",
    }


def _begin_source_derived(
    root: Path,
    onboarding: VoiceOnboardingRecord,
    intended_uses: list[str],
) -> dict[str, Any]:
    """Begin source-derived setup without asking for known arguments again.

    Persist only the initial authorisation and collection checkpoint. Building
    and activating a personalised style remain separate reviewed operations.

    Args:
        root (Path): Author workspace root.
        onboarding (VoiceOnboardingRecord): Generated undecided voice record.
        intended_uses (list[str]): Enabled content packs.

    Returns:
        dict[str, Any]: Concise source-collection result.
    """
    order = VoiceWorkOrder(
        display_name=onboarding.display_name,
        voice_id=onboarding.voice_id,
        author_name=onboarding.author_name,
        authorisation=Authorisation(
            confirmed=True,
            attested_by=onboarding.author_name,
            intended_uses=intended_uses,
        ),
        strategy=VoiceStrategy.SOURCE_DERIVED,
    )
    VoiceBuilder(root).save_work_order(order)
    save_voice_onboarding(
        root,
        VoiceOnboardingRecord(
            voice_id=onboarding.voice_id,
            display_name=onboarding.display_name,
            author_name=onboarding.author_name,
            status="collecting-sources",
            strategy=VoiceStrategy.SOURCE_DERIVED,
            selected_by=onboarding.author_name,
            selected_at=datetime.now(UTC).isoformat(),
            perspective_mode="pending-source-derived-activation",
        ),
    )
    save_score_preference(
        root,
        onboarding.voice_id,
        enabled=False,
        method="deterministic",
        selected_by=onboarding.author_name,
    )
    return {
        "status": "collecting-writing",
        "strategy": "source-derived",
        "author_name": onboarding.author_name,
        "next_step": "Add authorised writing, then build and review the personalised style.",
    }
