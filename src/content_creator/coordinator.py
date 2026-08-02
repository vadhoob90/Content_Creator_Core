from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .configuration import Configuration
from .coordinator_models import CoordinatorAction as CoordinatorAction
from .coordinator_models import ProviderStatus as ProviderStatus
from .coordinator_models import RunSummary as RunSummary
from .coordinator_models import VoiceStatus as VoiceStatus
from .coordinator_models import WorkspaceSnapshot as WorkspaceSnapshot
from .coordinator_models import action as coordinator_action
from .coordinator_models import operation as coordinator_operation
from .domain import RunState, RunStatus
from .health import WorkspaceHealth
from .packs import PackRegistry
from .storage import RunStore
from .voices import VoiceManifest, VoiceRegistry, load_voice_onboarding


class ContentCoordinator:
    """Read-only, deterministic interface for people and conversational hosts."""

    _action = staticmethod(coordinator_action)
    _operation = staticmethod(coordinator_operation)

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.configuration = Configuration(self.root)
        self.voice_registry = VoiceRegistry(self.root)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.1",
            "interface": "content-creator-coordinator",
            "principle": (
                "The coordinator translates user intent into Core commands; "
                "Core remains authoritative for state and approvals."
            ),
            "operations": [
                self._operation("workspace.inspect", ["coordinator", "context"]),
                self._operation("workspace.overview", ["overview"]),
                self._operation("workspace.start", ["start", "<request>"]),
                self._operation("run.plan", ["plan", "<request>"]),
                self._operation("run.create", ["run", "<request>"], mutates=True),
                self._operation(
                    "run.submission-status",
                    ["submission", "status", "<idempotency-key>"],
                ),
                self._operation("run.list", ["coordinator", "runs"]),
                self._operation(
                    "run.next-actions",
                    ["coordinator", "next-actions", "<run-id>"],
                ),
                self._operation(
                    "research.approve",
                    ["approve-research", "<run-id>"],
                    mutates=True,
                    approval=True,
                ),
                self._operation(
                    "research.reject",
                    ["reject-research", "<run-id>"],
                    mutates=True,
                    approval=True,
                ),
                self._operation(
                    "content.publish-local",
                    ["publish", "<run-id>"],
                    mutates=True,
                    approval=True,
                ),
                self._operation("voice.list", ["voice", "list"]),
                self._operation("voice.verify-all", ["voice", "verify-all"]),
                self._operation(
                    "voice.create",
                    ["voice", "create", "<arguments>"],
                    mutates=True,
                    approval=True,
                ),
                self._operation(
                    "voice.approve",
                    ["voice", "approve", "<voice-id>"],
                    mutates=True,
                    approval=True,
                ),
            ],
            "boundaries": {
                "chat_memory_is_state": False,
                "external_publication": False,
                "silent_voice_activation": False,
                "silent_research_approval": False,
                "silent_local_publication": False,
            },
        }

    def snapshot(self, run_limit: int = 10) -> WorkspaceSnapshot:
        policy = self.configuration.coordinator_policy
        packs = [item.id for item in PackRegistry(self.root).list()]
        voices = self._voices()
        active_ids = [item.voice_id for item in voices if item.active_status == "active"]
        warnings: List[str] = []
        default_voice = policy.get("default_voice")
        if default_voice and default_voice not in active_ids:
            warnings.append("Configured default voice is not active: {}".format(default_voice))
        if policy["default_pack"] not in packs:
            warnings.append(
                "Configured default pack is unavailable: {}".format(policy["default_pack"])
            )
        if not active_ids and not any(item.voice_id == "default" for item in voices):
            warnings.append("No active voice is available")
        health = WorkspaceHealth(self.root).report()
        if health["status"] != "ok":
            warnings.append("Workspace doctor checks require attention")
        provider = self._provider_status()
        if provider.status == "not-selected":
            warnings.append("No provider is selected")
        snapshot = WorkspaceSnapshot(
            workspace=str(self.root),
            is_workspace=(self.root / "content-creator.yaml").is_file()
            or (self.root / "profiles" / "registry.json").is_file(),
            coordinator=policy,
            provider=provider.name,
            provider_status=provider,
            packs=packs,
            voices=voices,
            active_voice_ids=active_ids,
            suggested_voice_id=default_voice if default_voice in active_ids else None,
            runs=self._run_summaries(run_limit),
            health=health,
            warnings=warnings,
            recommended_action=CoordinatorAction(
                id="pending",
                label="Inspect workspace state",
                command=["overview"],
            ),
        )
        snapshot.recommended_action = self._recommend(snapshot)
        return snapshot

    def context(self, run_limit: int = 10) -> Dict[str, Any]:
        return self.snapshot(run_limit).model_dump(mode="json")

    def runs(self, limit: int = 20) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "runs": [item.model_dump(mode="json") for item in self._run_summaries(limit)],
        }

    def next_actions(self, run_id: str) -> Dict[str, Any]:
        state = self.store.load(run_id)
        artifacts = self._artifacts(run_id)
        actions = self._actions_for_state(state, run_id)
        return {
            "schema_version": "1.1",
            "run_id": run_id,
            "status": state.status.value,
            "requires_human_input": (
                state.status
                in {
                    RunStatus.AWAITING_RESEARCH_APPROVAL,
                    RunStatus.READY,
                    RunStatus.NEEDS_AUTHOR,
                }
                or bool(state.pending_support_count)
            ),
            "diagnostic_attention_required": bool(state.pending_support_count),
            "diagnostic_summary": state.diagnostic_summary_path,
            "support_candidate": state.support_candidate_path,
            "last_error": state.last_error,
            "artifacts": artifacts,
            "actions": [item.model_dump(mode="json") for item in actions],
        }

    def _actions_for_state(self, state: RunState, run_id: str) -> List[CoordinatorAction]:
        routes = {
            RunStatus.AWAITING_RESEARCH_APPROVAL: self._research_actions,
            RunStatus.READY: self._reviewed_actions,
            RunStatus.NEEDS_AUTHOR: self._reviewed_actions,
            RunStatus.PUBLISHED: self._published_actions,
            RunStatus.FAILED: self._failed_actions,
        }
        handler = routes.get(state.status, self._fallback_actions)
        return handler(state, run_id)

    def _research_actions(self, state: RunState, run_id: str) -> List[CoordinatorAction]:
        del state
        return [
            self._action("review-research", "Review the research brief", artifact="research.json"),
            self._action(
                "approve-research",
                "Approve the research and resume",
                ["approve-research", run_id],
                mutates=True,
                confirmation=True,
            ),
            self._action(
                "reject-research",
                "Reject the research and stop",
                ["reject-research", run_id],
                mutates=True,
                confirmation=True,
            ),
        ]

    def _reviewed_actions(self, state: RunState, run_id: str) -> List[CoordinatorAction]:
        actions = []
        if state.final_draft_path:
            actions.append(
                self._action(
                    "review-final", "Review the current draft", artifact=state.final_draft_path
                )
            )
        if state.pending_support_count:
            actions.extend(self._diagnostic_publish_actions(state, run_id))
        elif state.status == RunStatus.READY:
            actions.append(
                self._action(
                    "publish-local",
                    "Move the approved draft into the repository",
                    ["publish", run_id],
                    mutates=True,
                    confirmation=True,
                )
            )
        else:
            actions.append(
                self._action(
                    "provide-author-direction", "Provide author direction before another run"
                )
            )
        return actions

    def _diagnostic_publish_actions(self, state: RunState, run_id: str) -> List[CoordinatorAction]:
        return [
            self._action(
                "review-support-candidate",
                "Review recovered Core issues before publication",
                artifact=state.support_candidate_path,
            ),
            self._action(
                "publish-only",
                "Publish without preparing a Core issue",
                ["publish", run_id, "--diagnostic-decision", "publish-only"],
                mutates=True,
                confirmation=True,
            ),
            self._action(
                "publish-and-prepare-issue",
                "Publish and prepare the Core issue for host submission",
                ["publish", run_id, "--diagnostic-decision", "prepare-issue"],
                mutates=True,
                confirmation=True,
            ),
        ]

    def _published_actions(self, state: RunState, run_id: str) -> List[CoordinatorAction]:
        del run_id
        actions = [
            self._action(
                "review-publication",
                "Inspect the repository publication",
                artifact=state.published_path,
            )
        ]
        if state.pending_support_count:
            actions.append(
                self._action(
                    "review-support-candidate",
                    "Review a Core issue discovered during publication",
                    artifact=state.support_candidate_path,
                )
            )
        return actions

    def _failed_actions(self, state: RunState, run_id: str) -> List[CoordinatorAction]:
        del run_id
        actions = [
            self._action(
                "inspect-failure", "Inspect the persisted error before deciding whether to retry"
            )
        ]
        if state.pending_support_count:
            actions.append(
                self._action(
                    "review-support-candidate",
                    "Review the fatal Core diagnostic",
                    artifact=state.support_candidate_path,
                )
            )
        return actions

    def _fallback_actions(self, state: RunState, run_id: str) -> List[CoordinatorAction]:
        del state
        return [
            self._action("inspect-status", "Inspect the persisted run state", ["status", run_id])
        ]

    def _run_summaries(self, limit: int) -> List[RunSummary]:
        states: List[RunState] = []
        for path in self.store.runs_dir.glob("*/state.json"):
            try:
                states.append(RunState.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        states.sort(key=lambda item: item.updated_at, reverse=True)
        return [
            RunSummary(
                run_id=state.id,
                status=state.status.value,
                topic=state.work_order.topic,
                content_pack=state.work_order.content_pack,
                voice_id=state.work_order.voice_id,
                updated_at=state.updated_at.isoformat(),
                requires_human_input=state.status
                in {
                    RunStatus.AWAITING_RESEARCH_APPROVAL,
                    RunStatus.READY,
                    RunStatus.NEEDS_AUTHOR,
                },
                incomplete=state.status != RunStatus.PUBLISHED,
            )
            for state in states[: max(0, limit)]
        ]

    def _voices(self) -> List[VoiceStatus]:
        registry = self.voice_registry.list()
        voice_ids = set(registry)
        voice_ids.update(
            path.parent.name for path in (self.root / "profiles").glob("*/onboarding.json")
        )
        voice_ids.update(
            path.parent.parent.name
            for path in (self.root / "profiles").glob("*/candidate/manifest.json")
        )
        if not voice_ids:
            return [
                VoiceStatus(
                    voice_id="default",
                    display_name="Default test profile",
                    active_status="active",
                    active_version="placeholder",
                    strategy="legacy-placeholder",
                )
            ]
        result = []
        for voice_id in sorted(voice_ids):
            active = registry.get(voice_id, {})
            onboarding = load_voice_onboarding(self.root, voice_id)
            candidate_path = self.root / "profiles" / voice_id / "candidate" / "manifest.json"
            candidate_status: Optional[str] = None
            if candidate_path.exists():
                try:
                    candidate_status = VoiceManifest.model_validate_json(
                        candidate_path.read_text(encoding="utf-8")
                    ).status.value
                except ValueError:
                    candidate_status = "invalid"
            result.append(
                VoiceStatus(
                    voice_id=voice_id,
                    display_name=active.get("display_name")
                    or (onboarding.display_name if onboarding else voice_id),
                    active_status=active.get("status"),
                    active_version=active.get("active_version"),
                    candidate_status=candidate_status,
                    onboarding_status=onboarding.status if onboarding else None,
                    strategy=active.get("strategy")
                    or (onboarding.strategy.value if onboarding and onboarding.strategy else None),
                )
            )
        return result

    def _provider_status(self) -> ProviderStatus:
        try:
            provider = self.configuration.default_provider
        except ValueError:
            return ProviderStatus()
        if provider in {"openai", "anthropic"}:
            variable = "{}_API_KEY".format(provider.upper())
            configured = bool(os.getenv(variable))
            return ProviderStatus(
                name=provider,
                status="configured" if configured else "missing-credentials",
                detail=variable,
            )
        executable = "codex" if provider == "codex-native" else "claude"
        return ProviderStatus(
            name=provider,
            status="available" if shutil.which(executable) else "unavailable",
            detail=executable,
        )

    @staticmethod
    def _recommend(snapshot: WorkspaceSnapshot) -> CoordinatorAction:
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
        for run in snapshot.runs:
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
        undecided = next(
            (voice for voice in snapshot.voices if voice.onboarding_status == "undecided"),
            None,
        )
        if undecided:
            return CoordinatorAction(
                id="choose-voice-route",
                label=(
                    "Choose source-derived voice or Clear Professional Starter for {}".format(
                        undecided.display_name
                    )
                ),
                command=["voice", "status", undecided.voice_id],
            )
        candidate = next(
            (voice for voice in snapshot.voices if voice.candidate_status),
            None,
        )
        if candidate:
            return CoordinatorAction(
                id="review-voice-candidate",
                label="Review the pending voice candidate",
                command=["voice", "status", candidate.voice_id],
            )
        if snapshot.provider_status.status in {
            "not-selected",
            "missing-credentials",
            "unavailable",
        }:
            return CoordinatorAction(
                id="select-provider",
                label="Select and verify a model provider",
                command=["provider", "--help"],
            )
        if not snapshot.active_voice_ids:
            return CoordinatorAction(
                id="create-voice",
                label="Create or activate a voice",
                command=["voice", "--help"],
            )
        return CoordinatorAction(
            id="create-content",
            label="Describe the content you want to create",
            command=["start", "<request>"],
        )

    def _artifacts(self, run_id: str) -> List[str]:
        directory = self.store.run_dir(run_id)
        return sorted(
            str(path.relative_to(self.root)) for path in directory.iterdir() if path.is_file()
        )
