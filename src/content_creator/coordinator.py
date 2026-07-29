from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .configuration import Configuration
from .domain import RunState, RunStatus
from .packs import PackRegistry
from .storage import RunStore
from .voices import VoiceManifest, VoiceRegistry, load_voice_onboarding


class ContentCoordinator:
    """Read-only, deterministic interface for conversational agent hosts."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.configuration = Configuration(self.root)
        self.voice_registry = VoiceRegistry(self.root)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "interface": "content-creator-coordinator",
            "principle": (
                "The coordinator translates user intent into Core commands; "
                "Core remains authoritative for state and approvals."
            ),
            "operations": [
                self._operation("workspace.inspect", ["coordinator", "context"]),
                self._operation("run.plan", ["plan", "<request>"]),
                self._operation("run.create", ["run", "<request>"], mutates=True),
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
                self._operation(
                    "voice.verify-all", ["voice", "verify-all"]
                ),
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

    def context(self, run_limit: int = 10) -> Dict[str, Any]:
        policy = self.configuration.coordinator_policy
        packs = [item.id for item in PackRegistry(self.root).list()]
        voices = self._voices()
        active_ids = [
            item["voice_id"]
            for item in voices
            if item.get("active_status") == "active"
        ]
        warnings: List[str] = []
        default_voice = policy.get("default_voice")
        if default_voice and default_voice not in active_ids:
            warnings.append(
                "Configured default voice is not active: {}".format(
                    default_voice
                )
            )
        if policy["default_pack"] not in packs:
            warnings.append(
                "Configured default pack is unavailable: {}".format(
                    policy["default_pack"]
                )
            )
        if not active_ids and not any(
            item["voice_id"] == "default" for item in voices
        ):
            warnings.append("No active voice is available")
        return {
            "schema_version": "1.0",
            "workspace": str(self.root),
            "coordinator": policy,
            "provider": self._configured_provider(),
            "packs": packs,
            "voices": voices,
            "active_voice_ids": active_ids,
            "suggested_voice_id": (
                default_voice if default_voice in active_ids else None
            ),
            "runs": self.runs(run_limit)["runs"],
            "warnings": warnings,
        }

    def runs(self, limit: int = 20) -> Dict[str, Any]:
        states: List[RunState] = []
        for path in self.store.runs_dir.glob("*/state.json"):
            try:
                states.append(
                    RunState.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValueError):
                continue
        states.sort(key=lambda item: item.updated_at, reverse=True)
        return {
            "schema_version": "1.0",
            "runs": [
                {
                    "run_id": state.id,
                    "status": state.status.value,
                    "topic": state.work_order.topic,
                    "content_pack": state.work_order.content_pack,
                    "voice_id": state.work_order.voice_id,
                    "updated_at": state.updated_at.isoformat(),
                    "requires_human_input": state.status
                    in {
                        RunStatus.AWAITING_RESEARCH_APPROVAL,
                        RunStatus.READY,
                        RunStatus.NEEDS_AUTHOR,
                    },
                }
                for state in states[: max(0, limit)]
            ],
        }

    def next_actions(self, run_id: str) -> Dict[str, Any]:
        state = self.store.load(run_id)
        actions: List[Dict[str, Any]] = []
        artifacts = self._artifacts(run_id)
        if state.status == RunStatus.AWAITING_RESEARCH_APPROVAL:
            actions.extend(
                [
                    self._action(
                        "review-research",
                        "Review the research brief",
                        None,
                        "research.json",
                    ),
                    self._action(
                        "approve-research",
                        "Approve the research and resume",
                        ["approve-research", run_id],
                        confirmation=True,
                    ),
                    self._action(
                        "reject-research",
                        "Reject the research and stop",
                        ["reject-research", run_id],
                        confirmation=True,
                    ),
                ]
            )
        elif state.status in {RunStatus.READY, RunStatus.NEEDS_AUTHOR}:
            if state.final_draft_path:
                actions.append(
                    self._action(
                        "review-final",
                        "Review the current draft",
                        None,
                        state.final_draft_path,
                    )
                )
            if state.status == RunStatus.READY:
                actions.append(
                    self._action(
                        "publish-local",
                        "Move the approved draft into the repository",
                        ["publish", run_id],
                        confirmation=True,
                    )
                )
            else:
                actions.append(
                    self._action(
                        "provide-author-direction",
                        "Provide author direction before another run",
                    )
                )
        elif state.status == RunStatus.PUBLISHED:
            actions.append(
                self._action(
                    "review-publication",
                    "Inspect the repository publication",
                    None,
                    state.published_path,
                )
            )
        elif state.status == RunStatus.FAILED:
            actions.append(
                self._action(
                    "inspect-failure",
                    "Inspect the persisted error before deciding whether to retry",
                )
            )
        else:
            actions.append(
                self._action(
                    "inspect-status",
                    "Inspect the persisted run state",
                    ["status", run_id],
                )
            )
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "status": state.status.value,
            "requires_human_input": state.status
            in {
                RunStatus.AWAITING_RESEARCH_APPROVAL,
                RunStatus.READY,
                RunStatus.NEEDS_AUTHOR,
            },
            "last_error": state.last_error,
            "artifacts": artifacts,
            "actions": actions,
        }

    def _voices(self) -> List[Dict[str, Any]]:
        registry = self.voice_registry.list()
        voice_ids = set(registry)
        voice_ids.update(
            path.parent.name
            for path in (self.root / "profiles").glob("*/onboarding.json")
        )
        voice_ids.update(
            path.parent.parent.name
            for path in (self.root / "profiles").glob("*/candidate/manifest.json")
        )
        if not voice_ids:
            return [
                {
                    "voice_id": "default",
                    "display_name": "Default test profile",
                    "active_status": "active",
                    "active_version": "placeholder",
                    "candidate_status": None,
                    "onboarding_status": None,
                    "strategy": "legacy-placeholder",
                }
            ]
        result = []
        for voice_id in sorted(voice_ids):
            active = registry.get(voice_id, {})
            onboarding = load_voice_onboarding(self.root, voice_id)
            candidate_path = (
                self.root
                / "profiles"
                / voice_id
                / "candidate"
                / "manifest.json"
            )
            candidate_status: Optional[str] = None
            if candidate_path.exists():
                try:
                    candidate_status = VoiceManifest.model_validate_json(
                        candidate_path.read_text(encoding="utf-8")
                    ).status.value
                except ValueError:
                    candidate_status = "invalid"
            result.append(
                {
                    "voice_id": voice_id,
                    "display_name": active.get("display_name")
                    or (onboarding.display_name if onboarding else voice_id),
                    "active_status": active.get("status"),
                    "active_version": active.get("active_version"),
                    "candidate_status": candidate_status,
                    "onboarding_status": onboarding.status if onboarding else None,
                    "strategy": active.get("strategy")
                    or (
                        onboarding.strategy.value
                        if onboarding and onboarding.strategy
                        else None
                    ),
                }
            )
        return result

    def _configured_provider(self) -> Optional[str]:
        try:
            return self.configuration.default_provider
        except ValueError:
            return None

    def _artifacts(self, run_id: str) -> List[str]:
        directory = self.store.run_dir(run_id)
        return sorted(
            str(path.relative_to(self.root))
            for path in directory.iterdir()
            if path.is_file()
        )

    @staticmethod
    def _operation(
        operation_id: str,
        command: List[str],
        *,
        mutates: bool = False,
        approval: bool = False,
    ) -> Dict[str, Any]:
        return {
            "id": operation_id,
            "command": command,
            "mutates_workspace": mutates,
            "requires_explicit_approval": approval,
        }

    @staticmethod
    def _action(
        action_id: str,
        label: str,
        command: Optional[List[str]] = None,
        artifact: Optional[str] = None,
        confirmation: bool = False,
    ) -> Dict[str, Any]:
        return {
            "id": action_id,
            "label": label,
            "command": command,
            "artifact": artifact,
            "requires_confirmation": confirmation,
        }
