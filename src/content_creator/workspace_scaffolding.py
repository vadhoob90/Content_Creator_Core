"""Provide workspace scaffolding contracts and behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

from .agent_resources import STANDARD_TEMPLATE
from .domain import utc_now
from .packs import PackRegistry
from .storage import RunStore, slugify
from .workspace_context_templates import RUNTIME_CONTEXT_TEMPLATE
from .workspace_templates import (
    LEARNINGS_README_TEMPLATE,
    PERSONALISATION_TEMPLATE,
    PROFILES_README_TEMPLATE,
    TECHNICAL_SETUP_TEMPLATE,
    VOICE_README_TEMPLATE,
    WorkspaceReadmeContext,
)


@dataclass(frozen=True)
class WorkspaceCreateRequest:
    """Represent a workspace create request."""

    name: str
    author_name: str
    voice_id: str | None = None
    voice_label: str | None = None
    packs: Iterable[str] | None = None
    agent_template: str = STANDARD_TEMPLATE
    core_source: str = "registry"
    core_url: str = "https://github.com/vadhoob90/Content_Creator_Core.git"
    core_ref: str = ""
    perspective_mode: str = "automatic"


@dataclass(frozen=True)
class WorkspaceIdentity:
    """Represent a workspace identity."""

    display_name: str
    author_name: str
    voice_id: str
    voice_label: str
    packs: list[str]
    dependency: str


@dataclass(frozen=True)
class WorkspaceServices:
    """Provide the services used to scaffold a workspace."""

    default_core_ref: str
    default_packs: list[str]
    dependency_resolver: Callable[[str, str, str], str]
    initialise: Callable[[Path, str, str | None], dict[str, Any]]
    write_if_missing: Callable[[Path, Path, str, list[str], list[str]], None]


def create_workspace(
    scaffolder: Any, request: WorkspaceCreateRequest, services: WorkspaceServices
) -> dict:
    """Create the workspace.

    Args:
        scaffolder (Any): The scaffolder value passed to create workspace.
        request (WorkspaceCreateRequest): The validated request that initiates the
            operation.
        services (WorkspaceServices): The services value passed to create workspace.

    Returns:
        dict: The created dict for workspace.
    """
    if not request.core_ref:
        request = WorkspaceCreateRequest(
            **{**request.__dict__, "core_ref": services.default_core_ref}
        )
    root = scaffolder.root
    _prepare_destination(root)
    identity = _validated_identity(root, request, services)
    created, preserved = _initialise_base(root, request, identity, services)
    _write_workspace_files(scaffolder, request, identity, created, preserved, services)
    return _result(root, request, identity, created, preserved)


def _prepare_destination(root: Path) -> None:
    """Prepare the destination.

    Args:
        root (Path): The workspace root directory.

    Returns:
        None: The callable updates destination state and returns no value.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    if root.exists() and not root.is_dir():
        raise ValueError(f"Workspace destination is not a directory: {root}")
    root.mkdir(parents=True, exist_ok=True)


def _validated_identity(
    root: Path, request: WorkspaceCreateRequest, services: WorkspaceServices
) -> WorkspaceIdentity:
    """Return the validated identity.

    Args:
        root (Path): The workspace root directory.
        request (WorkspaceCreateRequest): The validated request that initiates the
            operation.
        services (WorkspaceServices): The services value passed to validated identity.

    Returns:
        WorkspaceIdentity: The resulting workspace identity for validated identity.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    display_name = request.name.strip()
    author_name = request.author_name.strip()
    if not display_name or not author_name:
        label = "Workspace" if not display_name else "Author"
        raise ValueError(f"{label} name cannot be empty")
    if request.perspective_mode not in {"automatic", "explicit", "disabled"}:
        raise ValueError("Perspective mode must be automatic, explicit, or disabled")
    voice_label = (request.voice_label or f"{author_name} — General").strip()
    voice_id = slugify(request.voice_id or voice_label)
    if request.voice_id and voice_id != request.voice_id:
        raise ValueError("--voice-id must already be a repository-safe slug")
    selected_packs = list(dict.fromkeys(request.packs or services.default_packs))
    available = {pack.id for pack in PackRegistry(root).list()}
    unknown = sorted(set(selected_packs) - available)
    if unknown:
        raise ValueError(f"Unknown content packs: {', '.join(unknown)}")
    dependency = services.dependency_resolver(
        request.core_source, request.core_url, request.core_ref
    )
    return WorkspaceIdentity(
        display_name, author_name, voice_id, voice_label, selected_packs, dependency
    )


def _initialise_base(
    root: Path,
    request: WorkspaceCreateRequest,
    identity: WorkspaceIdentity,
    services: WorkspaceServices,
) -> tuple[list[str], list[str]]:
    """Initialise the base.

    Args:
        root (Path): The workspace root directory.
        request (WorkspaceCreateRequest): The validated request that initiates the
            operation.
        identity (WorkspaceIdentity): The identity value passed to initialise base.
        services (WorkspaceServices): The services value passed to initialise base.

    Returns:
        tuple[list[str], list[str]]: The resulting initialise base values in their
            documented order.
    """
    base_paths = (root / "profiles" / "registry.json", root / "content-creator.yaml")
    existed = {path: path.exists() for path in base_paths}
    base = services.initialise(root, request.agent_template, request.perspective_mode)
    if not existed[root / "content-creator.yaml"]:
        configuration_path = root / "content-creator.yaml"
        configuration = yaml.safe_load(configuration_path.read_text(encoding="utf-8"))
        configuration["coordinator"]["default_voice"] = identity.voice_id
        configuration["coordinator"]["default_pack"] = identity.packs[0]
        configuration["publication_provenance"] = {
            "policy": "required-for-new-publications",
            "receipts_directory": "publication-receipts",
            "semantic_review": "selected-perspectives",
        }
        RunStore._atomic_text(configuration_path, yaml.safe_dump(configuration, sort_keys=False))
    created = [
        entry if entry.startswith("learnings/") else f"agents/{entry}"
        for entry in base["agents"]["created"]
    ]
    preserved = [
        entry if entry.startswith("learnings/") else f"agents/{entry}"
        for entry in base["agents"]["preserved"]
    ]
    created.extend(base["skills"]["created"])
    preserved.extend(base["skills"]["preserved"])
    for path in base_paths:
        (preserved if existed[path] else created).append(str(path.relative_to(root)))
    return created, preserved


def _write_workspace_files(
    scaffolder: Any,
    request: WorkspaceCreateRequest,
    identity: WorkspaceIdentity,
    created: list[str],
    preserved: list[str],
    services: WorkspaceServices,
) -> None:
    """Write the workspace files.

    Render the thin workspace files, preserve existing author-owned content, and report
    every created or retained path.

    Args:
        scaffolder (Any): The scaffolder value passed to write workspace files.
        request (WorkspaceCreateRequest): The validated request that initiates the
            operation.
        identity (WorkspaceIdentity): The identity value passed to write workspace
            files.
        created (list[str]): The created collection consumed while write workspace
            files.
        preserved (list[str]): The preserved collection consumed while write workspace
            files.
        services (WorkspaceServices): The services value passed to write workspace
            files.

    Returns:
        None: The callable updates write workspace files state and returns no value.
    """
    root = scaffolder.root
    intended_uses = "\n".join(f"  --use {pack} \\" for pack in identity.packs).rstrip(" \\")
    readme_context = WorkspaceReadmeContext(
        identity.display_name,
        identity.author_name,
        identity.voice_id,
        identity.voice_label,
        identity.packs,
        request.core_ref,
        identity.dependency,
        intended_uses,
    )
    simple_files = {
        "pyproject.toml": scaffolder._pyproject(
            slugify(identity.display_name),
            identity.display_name,
            identity.author_name,
            identity.dependency,
        ),
        ".gitignore": scaffolder._gitignore(),
        ".env.example": scaffolder._environment(),
        "AGENTS.md": scaffolder._agents_guidance(
            identity.display_name, identity.author_name, identity.voice_id
        ),
        "CLAUDE.md": scaffolder._claude_guidance(),
        "README.md": scaffolder._readme(readme_context),
        "PERSONALISATION.md": PERSONALISATION_TEMPLATE.format(
            author_name=identity.author_name,
            voice_id=identity.voice_id,
        ),
        "profiles/README.md": PROFILES_README_TEMPLATE.format(
            voice_id=identity.voice_id,
        ),
        f"profiles/{identity.voice_id}/README.md": VOICE_README_TEMPLATE.format(
            voice_id=identity.voice_id,
            voice_label=identity.voice_label,
        ),
        "learnings/README.md": LEARNINGS_README_TEMPLATE,
        "docs/setup-and-technical-guide.md": TECHNICAL_SETUP_TEMPLATE.format(
            voice_id=identity.voice_id,
            first_pack=identity.packs[0],
        ),
        "docs/runtime-context.md": RUNTIME_CONTEXT_TEMPLATE.format(
            voice_id=identity.voice_id,
            first_pack=identity.packs[0],
        ),
        f"profiles/{identity.voice_id}/learnings/memory.json": json.dumps(
            {"version": 1, "records": []}, indent=2
        ),
        f"profiles/{identity.voice_id}/onboarding.json": _onboarding(identity),
        f"voice-material/{identity.voice_id}/source-urls.txt": _source_instructions(),
        "tests/test_workspace.py": scaffolder._smoke_test(identity.voice_id, identity.packs),
        "publication-receipts/baseline.json": json.dumps(
            {
                "schema_version": "1.0",
                "created_at": utc_now().isoformat(),
                "artifacts": [],
            },
            indent=2,
        ),
    }
    for relative, contents in simple_files.items():
        services.write_if_missing(root, root / relative, contents, created, preserved)
    for pack in identity.packs:
        services.write_if_missing(
            root, root / "content" / pack / "published" / ".gitkeep", "", created, preserved
        )


def _onboarding(identity: WorkspaceIdentity) -> str:
    """Return the onboarding.

    Args:
        identity (WorkspaceIdentity): The identity value passed to onboarding.

    Returns:
        str: The resulting text for onboarding.
    """
    record = {
        "schema_version": "1.0",
        "voice_id": identity.voice_id,
        "display_name": identity.voice_label,
        "author_name": identity.author_name,
        "status": "undecided",
        "strategy": None,
        "template_id": None,
        "selected_by": None,
        "selected_at": None,
        "perspective_mode": "pending",
        "perspective_disabled_reason": None,
    }
    return json.dumps(record, indent=2)


def _source_instructions() -> str:
    """Return the source instructions.

    Returns:
        str: The resulting text for source instructions.
    """
    return (
        "# Add one authorised public source URL per line.\n"
        "# Local Markdown, text, DOCX, PDF, and HTML files may be placed\n"
        "# in this directory and supplied with --documents."
    )


def _result(
    root: Path,
    request: WorkspaceCreateRequest,
    identity: WorkspaceIdentity,
    created: list[str],
    preserved: list[str],
) -> dict:
    """Return the result.

    Args:
        root (Path): The workspace root directory.
        request (WorkspaceCreateRequest): The validated request that initiates the
            operation.
        identity (WorkspaceIdentity): The identity value passed to result.
        created (list[str]): The created collection consumed while result.
        preserved (list[str]): The preserved collection consumed while result.

    Returns:
        dict: The resulting dict for result.
    """
    return {
        "status": "ok",
        "workspace": str(root),
        "name": identity.display_name,
        "author_name": identity.author_name,
        "voice_id": identity.voice_id,
        "voice_label": identity.voice_label,
        "packs": identity.packs,
        "core_dependency": identity.dependency,
        "perspective_mode": request.perspective_mode,
        "created": sorted(dict.fromkeys(created)),
        "preserved": sorted(dict.fromkeys(preserved)),
        "next_steps": [
            f"cd {root}",
            "uv sync --dev",
            "uv run content-creator --workspace . doctor",
            "Open the README and choose the source-derived or starter voice "
            f"route for {identity.voice_id}.",
        ],
    }
