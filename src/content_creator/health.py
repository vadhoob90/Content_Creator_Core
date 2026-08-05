"""Provide health capabilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .agent_resources import AgentWorkspace
from .configuration import Configuration
from .packs import PackRegistry
from .resource_paths import ResourceResolver


class WorkspaceHealth:
    """Represent the workspace health contract."""

    def __init__(self, root: Path):
        """Initialize the workspace health with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()

    def report(self) -> Dict[str, Any]:
        """Return the report.

        Returns:
            Dict[str, Any]: The structured resulting data for report.
        """
        configuration = Configuration(self.root)
        packs = PackRegistry(self.root).list()
        resources = ResourceResolver(self.root)
        repository_agents = AgentWorkspace(self.root).status()
        checks = {
            "model_catalogue": bool(configuration.models),
            "content_packs": [pack.id for pack in packs],
            "default_voice": resources.path("profiles/default/voice.md").exists(),
            "route_cases": resources.path("evals/cases/route-matrix.yaml").exists(),
            "repository_agents": repository_agents,
        }
        healthy = (
            checks["model_catalogue"]
            and bool(checks["content_packs"])
            and checks["default_voice"]
            and checks["route_cases"]
            and repository_agents["complete"]
        )
        return {"status": "ok" if healthy else "error", "checks": checks}
