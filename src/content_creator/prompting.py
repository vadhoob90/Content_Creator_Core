from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .domain import WorkOrder

ROLE_FILES = {
    "briefing-agent": "briefing-agent.md",
    "researcher": "researcher.md",
    "writer": "writer.md",
    "critic": "critic.md",
    "learning-extractor": "learning-extractor.md",
}

LEARNING_FILES = {
    "researcher": "researcher-learnings.md",
    "writer": "writer-learnings.md",
    "critic": "critic-learnings.md",
}


class PromptAssembler:
    def __init__(self, root: Path):
        self.root = root

    def system_prompt(self, role: str, order: Optional[WorkOrder] = None) -> str:
        parts = [self._read(self.root / "agents" / ROLE_FILES[role])]
        if role in LEARNING_FILES:
            parts.append(self._read(self.root / "agents" / LEARNING_FILES[role]))
        if role in {"writer", "critic", "learning-extractor"}:
            voice_id = order.voice_id if order else "default"
            parts.append(
                self._read(self.root / "profiles" / voice_id / "voice.md")
            )
        active = self._active_learnings(
            role, order.voice_id if order else "default"
        )
        if active:
            parts.append("## Active structured learnings\n\n" + "\n".join(active))
        if order and role in {"writer", "critic"}:
            rubric_paths = [
                self.root / "rubrics" / "core.yaml",
                self.root / "packs" / order.content_pack / "rubric.yaml",
                self.root
                / "rubrics"
                / "research-{}.yaml".format(order.research_depth.value),
            ]
            parts.append(
                "## Rubrics\n\n"
                + "\n\n".join(self._read(path) for path in rubric_paths)
            )
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def user_prompt(instruction: str, payload: Dict[str, Any]) -> str:
        return "{}\n\nINPUT\n{}".format(
            instruction, json.dumps(payload, indent=2, default=str, ensure_ascii=False)
        )

    @staticmethod
    def merge_payload(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for item in items:
            result.update(item)
        return result

    def _active_learnings(self, role: str, voice_id: str = "default"):
        path = self.root / "profiles" / voice_id / "learnings" / "memory.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            "- {}".format(item["principle"])
            for item in data.get("records", [])
            if item.get("role") == role and item.get("status") == "active"
        ]

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8").strip()
