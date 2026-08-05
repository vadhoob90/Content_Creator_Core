"""Provide workspace capabilities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .agent_resources import STANDARD_TEMPLATE, AgentWorkspace
from .storage import RunStore
from .version import VERSION
from .workspace_scaffolding import (
    WorkspaceCreateRequest,
    WorkspaceServices,
    create_workspace,
)
from .workspace_templates import WorkspaceTemplates

DEFAULT_CORE_URL = "https://github.com/vadhoob90/Content_Creator_Core.git"
DEFAULT_CORE_REF = "v{}".format(VERSION)
DEFAULT_CORE_SOURCE = "registry"
DEFAULT_PACKS = ["general-text"]
VERSION_TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")
README_CORE_START = "<!-- content-creator-core-dependency:start -->"
README_CORE_END = "<!-- content-creator-core-dependency:end -->"


def core_dependency(source: str, core_url: str, core_ref: str) -> str:
    """Return the core dependency.

    Args:
        source (str): The source value or artifact to process.
        core_url (str): The core url text processed when core dependency.
        core_ref (str): The core ref text processed when core dependency.

    Returns:
        str: The resulting text for core dependency.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    if source == "registry":
        match = VERSION_TAG.fullmatch(core_ref)
        if not match:
            raise ValueError("Registry dependencies require an immutable semantic version tag")
        return "content-creator=={}".format(match.group("version"))
    if source == "git":
        return "content-creator @ git+{}@{}".format(
            core_url.rstrip("/"),
            core_ref,
        )
    raise ValueError("Core source must be registry or git")


def readme_core_dependency(core_ref: str, dependency: str) -> str:
    """Render the small README section that Core upgrades may safely replace.

    Args:
        core_ref (str): The core ref text processed when readme core dependency.
        dependency (str): The pinned Core dependency declaration.

    Returns:
        str: The resulting text for readme core dependency.
    """
    return """{start}
## Core dependency

This workspace is built on the immutable Content Creator Core revision:
[`{core_ref}`]({core_url}/tree/{core_ref}). It installs that revision as
`{dependency}`. The dependency declaration in `pyproject.toml` and the
resolution in `uv.lock` are authoritative.
{end}""".format(
        start=README_CORE_START,
        end=README_CORE_END,
        core_ref=core_ref,
        core_url=DEFAULT_CORE_URL.removesuffix(".git"),
        dependency=dependency,
    )


def update_readme_core_dependency(text: str, core_ref: str, dependency: str) -> tuple[str, bool]:
    """Update only the generator-owned Core dependency block, when present.

    Args:
        text (str): The text to process.
        core_ref (str): The core ref text processed when update readme core dependency.
        dependency (str): The pinned Core dependency declaration.

    Returns:
        tuple[str, bool]: The resulting update readme core dependency values in their
            documented order.
    """
    start = text.find(README_CORE_START)
    end = text.find(README_CORE_END)
    if start < 0 or end < start:
        return text, False
    end += len(README_CORE_END)
    replacement = readme_core_dependency(core_ref, dependency)
    return text[:start] + replacement + text[end:], True


def _write_if_missing(
    root: Path,
    path: Path,
    content: str,
    created: List[str],
    preserved: List[str],
) -> None:
    """Write the if missing.

    Args:
        root (Path): The workspace root directory.
        path (Path): The filesystem path to inspect or update.
        content (str): The content to process.
        created (List[str]): The created collection consumed while write if missing.
        preserved (List[str]): The preserved collection consumed while write if missing.

    Returns:
        None: The callable updates write if missing state and returns no value.
    """
    relative = str(path.relative_to(root))
    if path.exists():
        preserved.append(relative)
        return
    RunStore._atomic_text(path, content.rstrip("\n"))
    created.append(relative)


def scaffold_skills(root: Path) -> Dict[str, List[str]]:
    """Return the scaffold skills.

    Args:
        root (Path): The workspace root directory.

    Returns:
        Dict[str, List[str]]: The structured resulting data for scaffold skills.
    """
    created: List[str] = []
    preserved: List[str] = []
    skills_root = Path(__file__).with_name("resources") / "skills"
    for source in sorted(skills_root.rglob("*")):
        if source.is_file():
            relative = source.relative_to(skills_root)
            _write_if_missing(
                root,
                root / ".agents" / "skills" / relative,
                source.read_text(encoding="utf-8"),
                created,
                preserved,
            )
    return {"created": created, "preserved": preserved}


def initialise_workspace(
    root: Path,
    agent_template: str = STANDARD_TEMPLATE,
    perspective_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Create the runtime-owned portion of a thin content workspace.

    Create runtime-owned workspace directories and baseline configuration without
    replacing repository-owned author files.

    Args:
        root (Path): The workspace root directory.
        agent_template (str): The agent template text processed when initialise
            workspace. Defaults to ``STANDARD_TEMPLATE``.
        perspective_mode (Optional[str]): The perspective mode text processed when
            initialise workspace. Defaults to ``None``.

    Returns:
        Dict[str, Any]: The structured resulting data for initialise workspace.
    """
    root = root.resolve()
    for path in (
        root / "profiles",
        root / "runs",
        root / ".voice-cache",
        root / "content" / "general-text" / "published",
    ):
        path.mkdir(parents=True, exist_ok=True)

    registry = root / "profiles" / "registry.json"
    if not registry.exists():
        RunStore._atomic_text(
            registry,
            json.dumps({"schema_version": "1.0", "profiles": {}}, indent=2),
        )

    agent_result = AgentWorkspace(root).scaffold(agent_template)
    skill_result = scaffold_skills(root)
    workspace_config = root / "content-creator.yaml"
    if not workspace_config.exists():
        metadata = agent_result["template_metadata"]
        configuration: Dict[str, Any] = {
            "schema_version": "1.0",
            "agent_template": {
                "name": metadata["name"],
                "version": metadata["version"],
            },
            "coordinator": {
                "name": "Content Creator Coordinator",
                "default_voice": None,
                "default_pack": "general-text",
                "ask_before_voice_change": True,
                "require_final_review": True,
                "external_publication": "disabled",
            },
            "diagnostics": {
                "enabled": True,
                "max_attempts": 2,
                "defer_recovered_until_publication": True,
            },
            "statistical_voice_score": {
                "enabled": False,
                "method": "deterministic",
                "minimum_sources": 20,
                "minimum_draft_words": 100,
                "outlier_iqr_multiplier": 1.5,
                "max_reported_outliers": 8,
            },
        }
        if perspective_mode:
            configuration["perspective"] = {
                "mode": perspective_mode,
                "allow_multiple": perspective_mode == "automatic",
                "ask_when_ambiguous": True,
                "show_resolution": True,
                "conflict_policy": "propose-update",
            }
        RunStore._atomic_text(
            workspace_config,
            yaml.safe_dump(configuration, sort_keys=False),
        )

    return {
        "status": "ok",
        "root": str(root),
        "agents": agent_result,
        "skills": skill_result,
    }


class WorkspaceScaffolder(WorkspaceTemplates):
    """Generate a complete thin repository that consumes Content Creator Core."""

    def __init__(self, destination: Path):
        """Initialize the workspace scaffolder with its required state and collaborators.

        Args:
            destination (Path): The destination filesystem path.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = destination.resolve()

    def create(self, request: WorkspaceCreateRequest) -> Dict[str, Any]:
        """Create the workspace scaffolder workflow.

        Args:
            request (WorkspaceCreateRequest): The validated request that initiates the
                operation.

        Returns:
            Dict[str, Any]: The structured created data for value.
        """
        services = WorkspaceServices(
            default_core_ref=DEFAULT_CORE_REF,
            default_packs=DEFAULT_PACKS,
            dependency_resolver=core_dependency,
            initialise=initialise_workspace,
            write_if_missing=_write_if_missing,
        )
        return create_workspace(self, request, services)
