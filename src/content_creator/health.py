from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .agent_resources import AgentWorkspace
from .configuration import Configuration
from .packs import PackRegistry
from .resource_paths import ResourceResolver


class WorkspaceHealth:
    """Offline workspace validation shared by doctor and the coordinator."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def report(self) -> Dict[str, Any]:
        configuration = Configuration(self.root)
        packs = PackRegistry(self.root).list()
        resources = ResourceResolver(self.root)
        checks = {
            "model_catalogue": bool(configuration.models),
            "content_packs": [pack.id for pack in packs],
            "default_voice": resources.path("profiles/default/voice.md").exists(),
            "route_cases": resources.path("evals/cases/route-matrix.yaml").exists(),
            "repository_agents": AgentWorkspace(self.root).status(),
        }
        healthy = (
            checks["model_catalogue"]
            and bool(checks["content_packs"])
            and checks["default_voice"]
            and checks["route_cases"]
            and checks["repository_agents"]["complete"]
        )
        return {"status": "ok" if healthy else "error", "checks": checks}
