"""Provide prompting capabilities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .agent_resources import LEARNING_FILES, AgentWorkspace
from .context_composition import ContextLayer
from .domain import LearningRole, PerspectiveSelection, WorkOrder
from .packs import PackRegistry
from .perspectives import PerspectiveEntry, PerspectiveRegistry
from .prompt_provenance import PromptComposition, PromptProvenance
from .resource_paths import ResourceResolver
from .voice_upgrade.epochs import epoch_path
from .voices import VoiceRegistry


class PromptAssembler:
    """Represent a prompt assembler."""

    def __init__(self, root: Path):
        """Initialize the prompt assembler with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.resources = ResourceResolver(self.root)
        self.agent_workspace = AgentWorkspace(self.root)
        self.provenance = PromptProvenance(self.root, self.resources.core)

    def system_prompt(self, role: str, order: Optional[WorkOrder] = None) -> str:
        """Return the system prompt.

        Args:
            role (str): The repository-owned agent role to execute.
            order (Optional[WorkOrder]): The work order that defines the requested content
                run. Defaults to ``None``.

        Returns:
            str: The resulting text for system prompt.
        """
        return self.compose(role, order).prompt

    def compose(self, role: str, order: Optional[WorkOrder] = None) -> PromptComposition:
        """Compose prompt text and exact loaded or skipped source provenance.

        Args:
            role (str): The repository-owned agent role to execute.
            order (Optional[WorkOrder]): Resolved content work order. Defaults to ``None``.

        Returns:
            PromptComposition: Prompt text and privacy-safe ordered layer evidence.
        """
        layers: list[ContextLayer] = []
        parts = self._base_prompt_parts(role, layers)
        self._append_voice_profile(parts, layers, role, order)
        self._append_perspectives(parts, layers, role, order)
        self._append_learnings(parts, layers, role, order)
        self._append_rubrics(parts, layers, role, order)
        return PromptComposition(prompt="\n\n---\n\n".join(parts), layers=layers)

    def _base_prompt_parts(self, role: str, layers: list[ContextLayer]) -> list[str]:
        """Return the base prompt parts.

        Args:
            role (str): The repository-owned agent role to execute.
            layers (list[ContextLayer]): Ordered provenance collection.

        Returns:
            list[str]: The resulting base prompt parts values in their documented order.
        """
        harness = self.agent_workspace.harness_path()
        contract = self.agent_workspace.contract_path(role)
        repository_agent = self.agent_workspace.role_path(role)
        parts = [
            self.provenance.load(layers, "core-harness", "Core harness", harness),
            self.provenance.load(layers, "core-role-contract", f"Core {role} contract", contract),
            "## Repository agent\n\n"
            + self.provenance.load(
                layers,
                "repository-agent",
                f"Workspace {role} agent",
                repository_agent,
            ),
        ]
        if role in LEARNING_FILES:
            policy = self.agent_workspace.learning_instructions_path(role)
            parts.append(
                "## Repository learning policy\n\n"
                + self.provenance.load(
                    layers,
                    "repository-learning-policy",
                    f"Workspace {role} learning policy",
                    policy,
                )
            )
        else:
            self.provenance.skip(
                layers,
                "repository-learning-policy",
                "Workspace learning policy",
                "workspace:not-applicable",
                "role-does-not-have-a-learning-policy",
            )
        return parts

    def _append_voice_profile(
        self,
        parts: list[str],
        layers: list[ContextLayer],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append voice profile.

        Args:
            parts (list[str]): The parts collection consumed while append voice profile.
            layers (list[ContextLayer]): Ordered provenance collection.
            role (str): The repository-owned agent role to execute.
            order (Optional[WorkOrder]): The work order that defines the requested content
                run.

        Returns:
            None: The callable updates append voice profile state and returns no value.
        """
        if role not in {"writer", "critic", "learning-extractor"}:
            self.provenance.skip(
                layers,
                "active-voice",
                "Active voice",
                "voice:not-applicable",
                "role-does-not-receive-voice",
                owner="voice",
            )
            return
        voice_id = order.voice_id if order else "default"
        resolved = VoiceRegistry(self.root).resolve(
            voice_id,
            order.voice_version if order else None,
            allow_inactive=bool(order and order.resolved_voice),
        )
        profile_root = self.resources.path(resolved["path"])
        profile = (
            profile_root / "profile.md"
            if (profile_root / "profile.md").exists()
            else profile_root / "voice.md"
        )
        text = self.provenance.load(
            layers,
            "active-voice",
            f"Active voice {voice_id}",
            profile,
            owner="voice",
            version=resolved.get("version"),
        )
        parts.append(self._resolved_voice_profile(resolved, text))

    def _append_perspectives(
        self,
        parts: list[str],
        layers: list[ContextLayer],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append perspectives.

        Append only the selected perspective profiles and their provenance to the prompt,
        preserving strict context isolation.

        Args:
            parts (list[str]): The parts collection consumed while append perspectives.
            layers (list[ContextLayer]): Ordered provenance collection.
            role (str): The repository-owned agent role to execute.
            order (Optional[WorkOrder]): The work order that defines the requested content
                run.

        Returns:
            None: The callable updates append perspectives state and returns no value.
        """
        eligible = {
            "researcher",
            "writer",
            "critic",
            "learning-extractor",
            "perspective-extractor",
            "perspective-evaluator",
        }
        if role not in eligible:
            self.provenance.skip(
                layers,
                "approved-perspectives",
                "Approved perspectives",
                "perspective:not-applicable",
                "role-does-not-receive-perspectives",
                owner="perspective",
            )
            return
        if not order or not order.perspective_selections:
            self.provenance.skip(
                layers,
                "approved-perspectives",
                "Approved perspectives",
                "perspective:none-selected",
                "no-approved-perspective-selected",
                owner="perspective",
            )
            return
        for index, selection in enumerate(order.perspective_selections):
            perspective_profile, perspective_root, perspective = self._perspective_profile(
                layers, order, selection, index
            )
            parts.append(
                "## Approved perspective context: {}\n\n".format(selection.context_id)
                + perspective_profile
            )
            constraints = perspective_root / "constraints.json"
            parts.append(
                "## Perspective constraints: {}\n\n".format(selection.context_id)
                + self.provenance.load(
                    layers,
                    "perspective-constraints",
                    f"Perspective constraints {selection.context_id}",
                    constraints,
                    owner="perspective",
                    version=perspective.get("version"),
                )
            )

    def _perspective_profile(
        self,
        layers: list[ContextLayer],
        order: WorkOrder,
        selection: PerspectiveSelection,
        index: int,
    ) -> tuple[str, Path, Dict[str, Any]]:
        """Load one isolated selected perspective profile and provenance.

        Resolve the selected immutable context, then load either its complete active
        profile or only the explicitly selected reusable entries.

        Args:
            layers (list[ContextLayer]): Ordered provenance collection.
            order (WorkOrder): Resolved content work order.
            selection (PerspectiveSelection): Approved selected context.
            index (int): Zero-based selection position.

        Returns:
            tuple[str, Path, Dict[str, Any]]: Profile text, root, and manifest data.
        """
        perspective = PerspectiveRegistry(self.root, order.voice_id).resolve(
            selection.context_id,
            selection.version,
            allow_inactive=order.resolved_perspective,
        )
        perspective_root = self.root / perspective["path"]
        selected_ids = (
            order.author_contribution.reusable_perspective_entry_ids
            if order.author_contribution and index == 0
            else []
        )
        entry_ids = selected_ids or perspective.get("active_entry_ids", [])
        if not selected_ids:
            profile_path = perspective_root / "perspective.md"
            return (
                self.provenance.load(
                    layers,
                    "approved-perspectives",
                    f"Approved perspective {selection.context_id}",
                    profile_path,
                    owner="perspective",
                    version=perspective.get("version"),
                    record_ids=entry_ids,
                ),
                perspective_root,
                perspective,
            )
        entries_path = perspective_root / "entries.json"
        entries = [
            PerspectiveEntry.model_validate(item)
            for item in json.loads(entries_path.read_text(encoding="utf-8"))
            if item.get("id") in selected_ids
        ]
        self.provenance.record_loaded(
            layers,
            "approved-perspectives",
            f"Approved perspective {selection.context_id}",
            entries_path,
            owner="perspective",
            version=perspective.get("version"),
            record_ids=entry_ids,
        )
        return (
            PerspectiveRegistry.render_profile(selection.context_id, entries),
            perspective_root,
            perspective,
        )

    def _append_learnings(
        self,
        parts: list[str],
        layers: list[ContextLayer],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append learnings.

        Args:
            parts (list[str]): The parts collection consumed while append learnings.
            layers (list[ContextLayer]): Ordered provenance collection.
            role (str): The repository-owned agent role to execute.
            order (Optional[WorkOrder]): The work order that defines the requested content
                run.

        Returns:
            None: The callable updates append learnings state and returns no value.
        """
        repository_path = self.root / "learnings" / "memory.json"
        repository_records = self._active_learning_records(repository_path, role)
        self.provenance.append_learning_scope(
            parts,
            layers,
            repository_path,
            repository_records,
            "repository",
        )
        voice_id = order.voice_id if order else "default"
        legacy_voice_path = self.root / "profiles" / voice_id / "learnings" / "memory.json"
        versioned_voice_path = (
            epoch_path(self.root, voice_id, str(order.voice_version))
            if order and order.voice_version
            else legacy_voice_path
        )
        voice_path = (
            versioned_voice_path if versioned_voice_path.is_file() else legacy_voice_path
        )
        voice_records = self._active_learning_records(voice_path, role)
        self.provenance.append_learning_scope(
            parts,
            layers,
            voice_path,
            voice_records,
            "voice",
        )

    def _append_rubrics(
        self,
        parts: list[str],
        layers: list[ContextLayer],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append rubrics.

        Compose only eligible pack policy while retaining explicit skip evidence for
        roles and sources that do not contribute to the provider prompt.

        Args:
            parts (list[str]): The parts collection consumed while append rubrics.
            layers (list[ContextLayer]): Ordered provenance collection.
            role (str): The repository-owned agent role to execute.
            order (Optional[WorkOrder]): The work order that defines the requested content
                run.

        Returns:
            None: The callable updates append rubrics state and returns no value.
        """
        if not order or role not in {"writer", "critic"}:
            reason = "no-work-order" if not order else "role-does-not-receive-rubrics"
            self.provenance.skip(
                layers,
                "rubrics",
                "Rubrics",
                "pack:not-applicable",
                reason,
                owner="pack",
            )
            self.provenance.skip(
                layers,
                "pack-instructions",
                "Pack instructions",
                "pack:not-applicable",
                reason,
                owner="pack",
            )
            return
        packs = PackRegistry(self.root)
        pack = packs.resolve(order.content_pack, order.pack_options)
        rubric_paths = self._rubric_paths(order, pack, packs)
        rubric_parts = []
        for path in rubric_paths:
            if path.exists():
                rubric_parts.append(
                    self.provenance.load(
                        layers,
                        "rubrics",
                        f"Rubric {path.name}",
                        path,
                        owner=self.provenance.owner(path),
                        version=pack.version,
                    )
                )
            else:
                self.provenance.skip(
                    layers,
                    "rubrics",
                    f"Rubric {path.name}",
                    self.provenance.source(path),
                    "rubric-file-is-missing",
                    owner=self.provenance.owner(path),
                )
        parts.append("## Rubrics\n\n" + "\n\n".join(rubric_parts))
        overlay = pack.prompts.get(role)
        if overlay:
            overlay_path = self.resources.path(overlay)
            parts.append(
                "## Pack instructions\n\n"
                + self.provenance.load(
                    layers,
                    "pack-instructions",
                    f"{pack.id} {role} instructions",
                    overlay_path,
                    owner=self.provenance.owner(overlay_path),
                    version=pack.version,
                )
            )
        else:
            self.provenance.skip(
                layers,
                "pack-instructions",
                f"{pack.id} {role} instructions",
                f"pack:{pack.id}",
                "selected-pack-has-no-role-overlay",
                owner="pack",
            )

    def _rubric_paths(self, order: WorkOrder, pack: Any, packs: PackRegistry) -> list[Path]:
        """Resolve the complete ordered rubric source list.

        Args:
            order (WorkOrder): Resolved content work order.
            pack (Any): Resolved content-pack contract.
            packs (PackRegistry): Registry resolving pack-owned paths.

        Returns:
            list[Path]: Core, pack, and research-depth rubrics in prompt order.
        """
        paths = [self.resources.path("rubrics/core.yaml")]
        if pack.rubric:
            paths.append(packs.path(order.content_pack, pack.rubric))
        paths.extend(self.resources.path(item) for item in pack.rubrics)
        paths.append(
            self.resources.path("rubrics/research-{}.yaml".format(order.research_depth.value))
        )
        return paths

    @staticmethod
    def _resolved_voice_profile(resolved: Dict[str, Any], profile: str) -> str:
        """Return the resolved voice profile.

        Args:
            resolved (Dict[str, Any]): The resolved collection consumed while resolved voice
                profile.
            profile (str): The resolved voice, perspective, or content profile.

        Returns:
            str: The resulting text for resolved voice profile.
        """
        if resolved.get("version_status") != "active":
            return profile
        candidate_only = (
            re.compile(
                r"^\|\s*Lifecycle status\s*\|.*candidate.*\|\s*$",
                re.IGNORECASE,
            ),
            re.compile(
                r"^\|\s*Approved voice patterns\s*\|\s*None\s*\|\s*$",
                re.IGNORECASE,
            ),
            re.compile(
                r"^>.*only an approved, activated version may guide publication.*$",
                re.IGNORECASE,
            ),
            re.compile(
                r"^>?.*observations.*not.*approved writing instructions.*$",
                re.IGNORECASE,
            ),
        )
        filtered = [
            line
            for line in profile.splitlines()
            if not any(pattern.match(line.strip()) for pattern in candidate_only)
        ]
        lifecycle = (
            "## Authoritative resolved voice lifecycle\n\n"
            "- Status: active\n"
            "- Version: {}\n"
            "- Authority: version manifest\n"
            "- This is an approved, active voice package. Candidate-only lifecycle "
            "claims in historical profile prose are not instructions."
        ).format(resolved["version"])
        return lifecycle + "\n\n" + "\n".join(filtered).strip()

    @staticmethod
    def user_prompt(instruction: str, payload: Dict[str, Any]) -> str:
        """Return the user prompt.

        Args:
            instruction (str): The instruction text processed when user prompt.
            payload (Dict[str, Any]): The structured payload to validate or persist.

        Returns:
            str: The resulting text for user prompt.
        """
        return "{}\n\nINPUT\n{}".format(
            instruction, json.dumps(payload, indent=2, default=str, ensure_ascii=False)
        )

    @staticmethod
    def merge_payload(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """Return the merge payload.

        Args:
            items (Iterable[Dict[str, Any]]): The items value passed to merge payload.

        Returns:
            Dict[str, Any]: The structured resulting data for merge payload.
        """
        result: Dict[str, Any] = {}
        for item in items:
            result.update(item)
        return result

    @staticmethod
    def _active_learning_records(path: Path, role: str) -> list[dict[str, Any]]:
        """Return active role-matched learning records.

        Args:
            path (Path): The filesystem path to inspect or update.
            role (str): The repository-owned agent role to execute.

        Returns:
            list[dict[str, Any]]: Active records in their persisted order.

        Raises:
            ValueError: If an input value violates the supported domain constraints.
        """
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        supported = {item.value for item in LearningRole}
        unsupported = [
            item
            for item in data.get("records", [])
            if item.get("status") == "active" and item.get("role") not in supported
        ]
        if unsupported:
            details = ", ".join(
                "{} ({})".format(item.get("id", "unknown id"), item.get("role"))
                for item in unsupported
            )
            raise ValueError(
                "Unsupported active learning role in {}: {}. Change each role to "
                "researcher, writer, or critic, or mark the record provisional/rejected "
                "for author review.".format(path, details)
            )
        return [
            item
            for item in data.get("records", [])
            if item.get("role") == role and item.get("status") == "active"
        ]

    @staticmethod
    def _active_learnings(path: Path, role: str) -> list[str]:
        """Return formatted active learnings for compatibility.

        Args:
            path (Path): Learning-memory source file.
            role (str): Repository-owned agent role.

        Returns:
            list[str]: Markdown bullets for active matching principles.
        """
        return [
            "- {}".format(item["principle"])
            for item in PromptAssembler._active_learning_records(path, role)
        ]

    @staticmethod
    def _read(path: Path) -> str:
        """Read the prompt assembler workflow.

        Args:
            path (Path): The filesystem path to inspect or update.

        Returns:
            str: The loaded text for value.
        """
        return path.read_text(encoding="utf-8").strip()
