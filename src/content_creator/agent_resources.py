from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from .resource_paths import ResourceResolver
from .storage import RunStore

ROLE_FILES = {
    "briefing-agent": "briefing-agent.md",
    "researcher": "researcher.md",
    "writer": "writer.md",
    "critic": "critic.md",
    "learning-extractor": "learning-extractor.md",
    "voice-analyst": "voice-analyst.md",
    "profile-critic": "profile-critic.md",
    "attribution-reviewer": "attribution-reviewer.md",
    "voice-evaluator": "voice-evaluator.md",
    "perspective-extractor": "perspective-extractor.md",
}

LEARNING_FILES = {
    "researcher": "researcher-learnings.md",
    "writer": "writer-learnings.md",
    "critic": "critic-learnings.md",
}

STANDARD_TEMPLATE = "standard"


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class AgentWorkspace:
    """Scaffold and inspect repository-owned agent instructions."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.resources = ResourceResolver(self.root)
        self.agents = self.root / "agents"
        self.learnings = self.root / "learnings" / "memory.json"

    def template_root(self, template: str = STANDARD_TEMPLATE) -> Path:
        path = self.resources.core / "agent-templates" / template / "agents"
        if not path.is_dir():
            raise ValueError("Unknown agent template: {}".format(template))
        return path

    def template_metadata(self, template: str = STANDARD_TEMPLATE) -> Dict[str, Any]:
        return json.loads(
            (self.template_root(template) / "template.json").read_text(encoding="utf-8")
        )

    def scaffold(self, template: str = STANDARD_TEMPLATE) -> Dict[str, Any]:
        template_root = self.template_root(template)
        self.agents.mkdir(parents=True, exist_ok=True)
        created: List[str] = []
        preserved: List[str] = []
        for source in sorted(template_root.iterdir()):
            if not source.is_file():
                continue
            destination = self.agents / source.name
            if destination.exists():
                preserved.append(source.name)
                continue
            RunStore._atomic_text(
                destination,
                source.read_text(encoding="utf-8").rstrip("\n"),
            )
            created.append(source.name)
        if not self.learnings.exists():
            RunStore._atomic_text(
                self.learnings,
                json.dumps({"version": 1, "records": []}, indent=2),
            )
            created.append("learnings/memory.json")
        else:
            preserved.append("learnings/memory.json")
        return {
            "template": template,
            "template_metadata": self.template_metadata(template),
            "created": created,
            "preserved": preserved,
            "status": self.status(template),
        }

    def status(self, template: str = STANDARD_TEMPLATE) -> Dict[str, Any]:
        self.template_root(template)
        expected = sorted(set(ROLE_FILES.values()) | set(LEARNING_FILES.values()))
        missing = [name for name in expected if not (self.agents / name).is_file()]
        return {
            "template": template,
            "complete": not missing and self.learnings.is_file(),
            "missing": missing,
            "template_provenance": (self.agents / "template.json").is_file(),
            "repository_learning_memory": self.learnings.is_file(),
        }

    def diff_template(self, template: str = STANDARD_TEMPLATE) -> Dict[str, Any]:
        template_root = self.template_root(template)
        expected = {path.name: path for path in template_root.iterdir() if path.is_file()}
        workspace = (
            {path.name: path for path in self.agents.iterdir() if path.is_file()}
            if self.agents.is_dir()
            else {}
        )
        changed = [
            name
            for name in sorted(expected.keys() & workspace.keys())
            if _digest(expected[name]) != _digest(workspace[name])
        ]
        return {
            "template": template,
            "changed": changed,
            "missing": sorted(expected.keys() - workspace.keys()),
            "unchanged": sorted(
                name for name in expected.keys() & workspace.keys() if name not in changed
            ),
            "additional": sorted(workspace.keys() - expected.keys()),
        }

    def role_path(self, role: str) -> Path:
        path = self.agents / ROLE_FILES[role]
        if not path.is_file():
            raise FileNotFoundError(
                "Repository agent is missing: {}. Run "
                "'content-creator --workspace . agents scaffold'.".format(path)
            )
        return path

    def learning_instructions_path(self, role: str) -> Path:
        path = self.agents / LEARNING_FILES[role]
        if not path.is_file():
            raise FileNotFoundError(
                "Repository learning instructions are missing: {}. Run "
                "'content-creator --workspace . agents scaffold'.".format(path)
            )
        return path

    def harness_path(self) -> Path:
        return self.resources.core / "contracts" / "agent-harness.md"

    def contract_path(self, role: str) -> Path:
        path = self.resources.core / "contracts" / "roles" / ROLE_FILES[role]
        if not path.is_file():
            raise FileNotFoundError("Core role contract is missing: {}".format(path))
        return path
