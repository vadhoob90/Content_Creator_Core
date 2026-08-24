"""Provide pure coordinator action and recommendation policy."""

from __future__ import annotations

from .coordinator_models import CoordinatorAction, WorkspaceSnapshot, action
from .domain import RunState, RunStatus


def actions_for_state(state: RunState, run_id: str) -> list[CoordinatorAction]:
    """Return safe next actions for a persisted lifecycle state.

    Keep lifecycle routing independent of workspace reads so every state and
    diagnostic branch can be characterised as a deterministic policy table.

    Args:
        state (RunState): Persisted lifecycle state being routed.
        run_id (str): Stable run identifier used in generated commands.

    Returns:
        list[CoordinatorAction]: Ordered actions safe for the current state.
    """
    if state.status == RunStatus.AWAITING_RESEARCH_APPROVAL:
        return [
            action("review-research", "Review the research brief", artifact="research.json"),
            action(
                "approve-research",
                "Approve the research and resume",
                ["approve-research", run_id],
                mutates=True,
                confirmation=True,
            ),
            action(
                "reject-research",
                "Reject the research and stop",
                ["reject-research", run_id],
                mutates=True,
                confirmation=True,
            ),
        ]
    if state.status in {RunStatus.READY, RunStatus.NEEDS_AUTHOR}:
        return _reviewed_actions(state, run_id)
    if state.status == RunStatus.PUBLISHED:
        actions = [
            action(
                "review-publication",
                "Inspect the repository publication",
                artifact=state.published_path,
            )
        ]
        if state.pending_learning_count:
            actions.append(
                action(
                    "retry-learning",
                    "Retry the pending publication learning update",
                    ["learn", run_id, "--retry-pending"],
                    mutates=True,
                    confirmation=True,
                )
            )
        if state.pending_support_count:
            actions.append(
                action(
                    "review-support-candidate",
                    "Review a Core issue discovered during publication",
                    artifact=state.support_candidate_path,
                )
            )
        return actions
    if state.status == RunStatus.FAILED:
        actions = [
            action(
                "inspect-failure",
                "Inspect the persisted error before deciding whether to retry",
            )
        ]
        if state.pending_support_count:
            actions.append(
                action(
                    "review-support-candidate",
                    "Review the fatal Core diagnostic",
                    artifact=state.support_candidate_path,
                )
            )
        return actions
    return [action("inspect-status", "Inspect the persisted run state", ["status", run_id])]


def _reviewed_actions(state: RunState, run_id: str) -> list[CoordinatorAction]:
    """Return review, diagnostic, or publication actions for a completed draft.

    Require diagnostic disposition before offering ordinary local publication,
    while keeping author-blocked drafts non-mutating.

    Args:
        state (RunState): Ready or author-blocked lifecycle state.
        run_id (str): Stable run identifier used in generated commands.

    Returns:
        list[CoordinatorAction]: Ordered review and publication choices.
    """
    actions = []
    if state.final_draft_path:
        actions.append(
            action("review-final", "Review the current draft", artifact=state.final_draft_path)
        )
    if state.pending_support_count:
        actions.extend(
            [
                action(
                    "review-support-candidate",
                    "Review recovered Core issues before publication",
                    artifact=state.support_candidate_path,
                ),
                action(
                    "publish-only",
                    "Publish without preparing a Core issue",
                    ["publish", run_id, "--diagnostic-decision", "publish-only"],
                    mutates=True,
                    confirmation=True,
                ),
                action(
                    "publish-and-prepare-issue",
                    "Publish and prepare the Core issue for host submission",
                    ["publish", run_id, "--diagnostic-decision", "prepare-issue"],
                    mutates=True,
                    confirmation=True,
                ),
            ]
        )
    elif state.status == RunStatus.READY:
        actions.append(
            action(
                "publish-local",
                "Move the approved draft into the repository",
                ["publish", run_id],
                mutates=True,
                confirmation=True,
            )
        )
    else:
        actions.append(
            action("provide-author-direction", "Provide author direction before another run")
        )
    return actions


def recommend_action(snapshot: WorkspaceSnapshot) -> CoordinatorAction:
    """Return the next safe author action from a workspace snapshot.

    Prioritise interrupted work and pending approvals before suggesting new
    setup or content work, without reading or mutating workspace state.

    Args:
        snapshot (WorkspaceSnapshot): Complete coordinator view to evaluate.

    Returns:
        CoordinatorAction: Highest-priority safe author action.
    """
    if not snapshot.is_workspace:
        return CoordinatorAction(
            id="create-workspace",
            label="Create an author-owned content workspace",
            command=[
                "workspace",
                "create",
                "<directory>",
                "--author-name",
                "<author-name>",
            ],
            mutates_workspace=True,
        )
    existing_run = _existing_run_action(snapshot)
    if existing_run:
        return existing_run
    setup = _setup_action(snapshot)
    if setup:
        return setup
    return CoordinatorAction(
        id="create-content",
        label="Describe the content you want to create",
        command=["start", "<request>"],
    )


def _existing_run_action(snapshot: WorkspaceSnapshot) -> CoordinatorAction | None:
    """Return the highest-priority action for interrupted or reviewable work.

    Args:
        snapshot (WorkspaceSnapshot): Complete coordinator view to evaluate.

    Returns:
        CoordinatorAction | None: Existing-run action when one takes priority.
    """
    for run in (item for item in snapshot.runs if item.authoritative):
        if run.status == RunStatus.AWAITING_RESEARCH_APPROVAL.value:
            return CoordinatorAction(
                id="review-research",
                label="Review the interrupted run's research checkpoint",
                command=["coordinator", "next-actions", run.run_id],
            )
        if run.status in {RunStatus.READY.value, RunStatus.NEEDS_AUTHOR.value}:
            return CoordinatorAction(
                id="review-draft",
                label="Review the completed draft and its next actions",
                command=["coordinator", "next-actions", run.run_id],
            )
    return None


def _setup_action(snapshot: WorkspaceSnapshot) -> CoordinatorAction | None:
    """Return the next voice or provider prerequisite action.

    Preserve lifecycle decision priority while translating first-run gaps into
    the smaller setup command surface.

    Args:
        snapshot (WorkspaceSnapshot): Complete coordinator view to evaluate.

    Returns:
        CoordinatorAction | None: Setup action when content is not ready.
    """
    undecided = next(
        (voice for voice in snapshot.voices if voice.onboarding_status == "undecided"), None
    )
    if undecided:
        return CoordinatorAction(
            id="choose-voice-route",
            label=(
                "Choose personalised writing or the neutral starter for {}".format(
                    undecided.display_name
                )
            ),
            command=["setup"],
        )
    candidate = next(
        (voice for voice in snapshot.voices if voice.candidate_decision == "pending"), None
    )
    if candidate:
        return CoordinatorAction(
            id="review-voice-candidate",
            label="Review the pending voice candidate",
            command=["personalisation", "show"],
        )
    collecting = next(
        (voice for voice in snapshot.voices if voice.onboarding_status == "collecting-sources"),
        None,
    )
    if collecting:
        return CoordinatorAction(
            id="continue-voice-onboarding",
            label="Add authorised writing for personalised setup",
            command=[
                "voice",
                "add-sources",
                collecting.voice_id,
                "--documents",
                "<path-to-writing>",
            ],
            mutates_workspace=True,
        )
    eligible_upgrade = next((voice for voice in snapshot.voices if voice.upgrade_eligible), None)
    if eligible_upgrade:
        return CoordinatorAction(
            id="plan-voice-upgrade",
            label="Review new evidence and learning eligible for voice evolution",
            command=eligible_upgrade.upgrade_plan_command,
        )
    if not snapshot.active_voice_ids:
        return CoordinatorAction(
            id="create-voice",
            label="Create or activate a writing style",
            command=["voice", "--help"],
        )
    if snapshot.provider_status.status != "verified":
        command = ["setup"]
        if snapshot.provider_status.name:
            command = ["setup", "provider", snapshot.provider_status.name]
            if snapshot.provider_status.name in {"anthropic", "bedrock", "openai"}:
                command.append("--confirm-api-billing")
        return CoordinatorAction(
            id="select-provider",
            label="Choose and verify a model connection",
            command=command,
            mutates_workspace=bool(snapshot.provider_status.name),
            requires_confirmation=bool(snapshot.provider_status.name),
        )
    return None
