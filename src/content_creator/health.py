"""Provide health capabilities."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Dict

from .agent_resources import AgentWorkspace
from .configuration import Configuration
from .packs import PackRegistry
from .resource_paths import ResourceResolver
from .version import VERSION

_CORE_PIN = re.compile(r"^content-creator==(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


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
        workspace_pin = self._workspace_core_pin()
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
        warnings = []
        if workspace_pin and workspace_pin != VERSION:
            warnings.append(
                "Workspace pins content-creator=={} but this command is running Core {}. "
                "Use the workspace environment or preview an intentional upgrade with "
                "'workspace upgrade --to v{}'.".format(workspace_pin, VERSION, VERSION)
            )
        return {
            "status": "ok" if healthy else "error",
            "core_version": VERSION,
            "workspace_core_version": workspace_pin,
            "warnings": warnings,
            "checks": checks,
        }

    def _workspace_core_pin(self) -> str | None:
        """Return the exact registry pin declared by the workspace, when present.

        Returns:
            str | None: Exact semantic version pin, or ``None`` when not declared.
        """
        pyproject = self.root / "pyproject.toml"
        if not pyproject.is_file():
            return None
        try:
            project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        except (OSError, tomllib.TOMLDecodeError):
            return None
        for dependency in project.get("dependencies", []):
            match = _CORE_PIN.fullmatch(str(dependency).strip())
            if match:
                return match.group("version")
        return None
