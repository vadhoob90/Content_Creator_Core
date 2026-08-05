"""Provide prompting capabilities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .agent_resources import LEARNING_FILES, AgentWorkspace
from .domain import LearningRole, WorkOrder
from .packs import PackRegistry
from .perspectives import PerspectiveEntry, PerspectiveRegistry
from .resource_paths import ResourceResolver
from .voices import VoiceRegistry


class PromptAssembler:
    """Represent a prompt assembler."""

    def __init__(self, root: Path):
        """Initialize the prompt assembler."""
        self.root = root.resolve()
        self.resources = ResourceResolver(self.root)
        self.agent_workspace = AgentWorkspace(self.root)

    def system_prompt(self, role: str, order: Optional[WorkOrder] = None) -> str:
        """Return the system prompt."""
        parts = self._base_prompt_parts(role)
        self._append_voice_profile(parts, role, order)
        self._append_perspectives(parts, role, order)
        self._append_learnings(parts, role, order)
        self._append_rubrics(parts, role, order)
        return "\n\n---\n\n".join(parts)

    def _base_prompt_parts(self, role: str) -> list[str]:
        """Return the base prompt parts."""
        parts = [
            self._read(self.agent_workspace.harness_path()),
            self._read(self.agent_workspace.contract_path(role)),
            "## Repository agent\n\n" + self._read(self.agent_workspace.role_path(role)),
        ]
        if role in LEARNING_FILES:
            parts.append(
                "## Repository learning policy\n\n"
                + self._read(self.agent_workspace.learning_instructions_path(role))
            )
        return parts

    def _append_voice_profile(
        self,
        parts: list[str],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append voice profile."""
        if role in {"writer", "critic", "learning-extractor"}:
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
            parts.append(self._resolved_voice_profile(resolved, self._read(profile)))

    def _append_perspectives(
        self,
        parts: list[str],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append perspectives."""
        if (
            order
            and order.perspective_selections
            and role
            in {
                "researcher",
                "writer",
                "critic",
                "learning-extractor",
                "perspective-extractor",
            }
        ):
            for index, selection in enumerate(order.perspective_selections):
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
                if selected_ids:
                    entries = [
                        PerspectiveEntry.model_validate(item)
                        for item in json.loads(
                            (perspective_root / "entries.json").read_text(encoding="utf-8")
                        )
                        if item.get("id") in selected_ids
                    ]
                    perspective_profile = PerspectiveRegistry.render_profile(
                        selection.context_id,
                        entries,
                    )
                else:
                    perspective_profile = self._read(perspective_root / "perspective.md")
                parts.append(
                    "## Approved perspective context: {}\n\n".format(selection.context_id)
                    + perspective_profile
                )
                parts.append(
                    "## Perspective constraints: {}\n\n".format(selection.context_id)
                    + self._read(perspective_root / "constraints.json")
                )

    def _append_learnings(
        self,
        parts: list[str],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append learnings."""
        repository_learnings = self._active_learnings(
            self.root / "learnings" / "memory.json",
            role,
        )
        if repository_learnings:
            parts.append("## Active repository learnings\n\n" + "\n".join(repository_learnings))
        voice_id = order.voice_id if order else "default"
        voice_learnings = self._active_learnings(
            self.root / "profiles" / voice_id / "learnings" / "memory.json",
            role,
        )
        if voice_learnings:
            parts.append("## Active voice learnings\n\n" + "\n".join(voice_learnings))

    def _append_rubrics(
        self,
        parts: list[str],
        role: str,
        order: Optional[WorkOrder],
    ) -> None:
        """Return the append rubrics."""
        if order and role in {"writer", "critic"}:
            packs = PackRegistry(self.root)
            pack = packs.resolve(order.content_pack, order.pack_options)
            rubric_paths = [self.resources.path("rubrics/core.yaml")]
            if pack.rubric:
                rubric_paths.append(packs.path(order.content_pack, pack.rubric))
            rubric_paths.extend(self.resources.path(item) for item in pack.rubrics)
            rubric_paths.append(
                self.resources.path("rubrics/research-{}.yaml".format(order.research_depth.value))
            )
            parts.append(
                "## Rubrics\n\n"
                + "\n\n".join(self._read(path) for path in rubric_paths if path.exists())
            )
            overlay = pack.prompts.get(role)
            if overlay:
                overlay_path = self.resources.path(overlay)
                parts.append("## Pack instructions\n\n" + self._read(overlay_path))

    @staticmethod
    def _resolved_voice_profile(resolved: Dict[str, Any], profile: str) -> str:
        """Return the resolved voice profile."""
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
        """Return the user prompt."""
        return "{}\n\nINPUT\n{}".format(
            instruction, json.dumps(payload, indent=2, default=str, ensure_ascii=False)
        )

    @staticmethod
    def merge_payload(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """Return the merge payload."""
        result: Dict[str, Any] = {}
        for item in items:
            result.update(item)
        return result

    @staticmethod
    def _active_learnings(path: Path, role: str) -> list[str]:
        """Return the active learnings."""
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
            "- {}".format(item["principle"])
            for item in data.get("records", [])
            if item.get("role") == role and item.get("status") == "active"
        ]

    @staticmethod
    def _read(path: Path) -> str:
        """Read prompt assembler."""
        return path.read_text(encoding="utf-8").strip()
