"""Single-responsibility phases for generating a thin workspace."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from .agent_resources import STANDARD_TEMPLATE
from .packs import PackRegistry
from .storage import RunStore, slugify


@dataclass(frozen=True)
class WorkspaceCreateRequest:
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
    display_name: str
    author_name: str
    voice_id: str
    voice_label: str
    packs: list[str]
    dependency: str


def create_workspace(scaffolder: Any, request: WorkspaceCreateRequest) -> dict:
    from .workspace import DEFAULT_CORE_REF

    if not request.core_ref:
        request = WorkspaceCreateRequest(**{**request.__dict__, "core_ref": DEFAULT_CORE_REF})
    root = scaffolder.root
    _prepare_destination(root)
    identity = _validated_identity(root, request)
    created, preserved = _initialise_base(root, request, identity)
    _write_workspace_files(scaffolder, request, identity, created, preserved)
    return _result(root, request, identity, created, preserved)


def _prepare_destination(root: Path) -> None:
    if root.exists() and not root.is_dir():
        raise ValueError(f"Workspace destination is not a directory: {root}")
    root.mkdir(parents=True, exist_ok=True)


def _validated_identity(root: Path, request: WorkspaceCreateRequest) -> WorkspaceIdentity:
    from .workspace import DEFAULT_PACKS, core_dependency

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
    selected_packs = list(dict.fromkeys(request.packs or DEFAULT_PACKS))
    available = {pack.id for pack in PackRegistry(root).list()}
    unknown = sorted(set(selected_packs) - available)
    if unknown:
        raise ValueError(f"Unknown content packs: {', '.join(unknown)}")
    dependency = core_dependency(request.core_source, request.core_url, request.core_ref)
    return WorkspaceIdentity(
        display_name, author_name, voice_id, voice_label, selected_packs, dependency
    )


def _initialise_base(
    root: Path, request: WorkspaceCreateRequest, identity: WorkspaceIdentity
) -> tuple[list[str], list[str]]:
    from .workspace import initialise_workspace

    base_paths = (root / "profiles" / "registry.json", root / "content-creator.yaml")
    existed = {path: path.exists() for path in base_paths}
    base = initialise_workspace(root, request.agent_template, request.perspective_mode)
    if not existed[root / "content-creator.yaml"]:
        configuration_path = root / "content-creator.yaml"
        configuration = yaml.safe_load(configuration_path.read_text(encoding="utf-8"))
        configuration["coordinator"]["default_voice"] = identity.voice_id
        configuration["coordinator"]["default_pack"] = identity.packs[0]
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
) -> None:
    from .workspace import _write_if_missing
    from .workspace_templates import WorkspaceReadmeContext

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
        f"profiles/{identity.voice_id}/learnings/memory.json": json.dumps(
            {"version": 1, "records": []}, indent=2
        ),
        f"profiles/{identity.voice_id}/onboarding.json": _onboarding(identity),
        f"voice-material/{identity.voice_id}/source-urls.txt": _source_instructions(),
        "tests/test_workspace.py": scaffolder._smoke_test(identity.voice_id, identity.packs),
    }
    for relative, contents in simple_files.items():
        _write_if_missing(root, root / relative, contents, created, preserved)
    for pack in identity.packs:
        _write_if_missing(
            root, root / "content" / pack / "published" / ".gitkeep", "", created, preserved
        )


def _onboarding(identity: WorkspaceIdentity) -> str:
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
