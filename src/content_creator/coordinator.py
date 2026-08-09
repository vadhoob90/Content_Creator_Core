"""Provide coordinator capabilities."""

from __future__ import annotations

import logging
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
from .coordinator_models import operation as coordinator_operation
from .coordinator_policy import actions_for_state, recommend_action
from .domain import RunState, RunStatus
from .health import WorkspaceHealth
from .packs import PackRegistry
from .storage import RunStore
from .upgrade_audit import coordinator_upgrade_operations, latest_upgrade_report
from .voice_rejection import candidate_decision
from .voices import VoiceManifest, VoiceRegistry, load_voice_onboarding

logger = logging.getLogger(__name__)


class ContentCoordinator:
    """Represent the content coordinator contract."""

    _operation = staticmethod(coordinator_operation)
    _actions_for_state = staticmethod(actions_for_state)
    _recommend = staticmethod(recommend_action)

    def __init__(self, root: Path):
        """Initialize the content coordinator with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.configuration = Configuration(self.root)
        self.voice_registry = VoiceRegistry(self.root)

    def capabilities(self) -> Dict[str, Any]:
        """Return the capabilities.

        Inspect repository configuration and optional dependencies to report which author-
        facing workflows are currently available.

        Returns:
            Dict[str, Any]: The structured resulting data for capabilities.
        """
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
                *coordinator_upgrade_operations(),
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
        """Return the snapshot.

        Combine workspace health, run state, voice state, and recommended actions into one
        deterministic coordinator view.

        Args:
            run_limit (int): The run limit value that controls snapshot. Defaults to ``10``.

        Returns:
            WorkspaceSnapshot: The resulting workspace snapshot for snapshot.
        """
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
        """Return the context.

        Args:
            run_limit (int): The run limit value that controls context. Defaults to ``10``.

        Returns:
            Dict[str, Any]: The structured resulting data for context.
        """
        result = self.snapshot(run_limit).model_dump(mode="json")
        result["latest_upgrade_compatibility"] = latest_upgrade_report(self.root)
        return result

    def runs(self, limit: int = 20) -> Dict[str, Any]:
        """Return the runs.

        Args:
            limit (int): The maximum number of records to return or process. Defaults to
                ``20``.

        Returns:
            Dict[str, Any]: The structured resulting data for runs.
        """
        return {
            "schema_version": "1.0",
            "runs": [item.model_dump(mode="json") for item in self._run_summaries(limit)],
        }

    def next_actions(self, run_id: str) -> Dict[str, Any]:
        """Return the next actions.

        Args:
            run_id (str): The stable identifier for the content run.

        Returns:
            Dict[str, Any]: The structured resulting data for next actions.
        """
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

    def _run_summaries(self, limit: int) -> List[RunSummary]:
        """Run the summaries.

        Args:
            limit (int): The maximum number of records to return or process.

        Returns:
            List[RunSummary]: The execution summaries values in their documented order.
        """
        states: List[RunState] = []
        for path in self.store.runs_dir.glob("*/state.json"):
            try:
                states.append(RunState.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                logger.warning(
                    "Skipping unreadable run state at %s (%s)",
                    path.relative_to(self.root),
                    exc.__class__.__name__,
                )
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
        """Return the voices.

        Read the voice registry and summarize active, candidate, and source-derived voice
        state without mutating the workspace.

        Returns:
            List[VoiceStatus]: The resulting voices values in their documented order.
        """
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
            decision = candidate_decision(self.root, voice_id, active)
            result.append(
                VoiceStatus(
                    voice_id=voice_id,
                    display_name=active.get("display_name")
                    or (onboarding.display_name if onboarding else voice_id),
                    active_status=active.get("status"),
                    active_version=active.get("active_version"),
                    candidate_status=candidate_status,
                    candidate_decision=decision["status"],
                    candidate_hash=decision.get("candidate_hash"),
                    onboarding_status=onboarding.status if onboarding else None,
                    strategy=active.get("strategy")
                    or (onboarding.strategy.value if onboarding and onboarding.strategy else None),
                )
            )
        return result

    def _provider_status(self) -> ProviderStatus:
        """Return the provider status.

        Returns:
            ProviderStatus: The resulting provider status for provider status.
        """
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

    def _artifacts(self, run_id: str) -> List[str]:
        """Return the artifacts.

        Args:
            run_id (str): The stable identifier for the content run.

        Returns:
            List[str]: The resulting artifacts values in their documented order.
        """
        directory = self.store.run_dir(run_id)
        return sorted(
            str(path.relative_to(self.root)) for path in directory.iterdir() if path.is_file()
        )
