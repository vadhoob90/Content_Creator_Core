from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from .agent_resources import STANDARD_TEMPLATE, AgentWorkspace
from .packs import PackRegistry
from .storage import RunStore, slugify
from .version import VERSION
from .workspace_templates import WorkspaceTemplates

DEFAULT_CORE_URL = "https://github.com/vadhoob90/Content_Creator_Core.git"
DEFAULT_CORE_REF = "v{}".format(VERSION)
DEFAULT_CORE_SOURCE = "registry"
DEFAULT_PACKS = ["general-text"]
VERSION_TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")
README_CORE_START = "<!-- content-creator-core-dependency:start -->"
README_CORE_END = "<!-- content-creator-core-dependency:end -->"


def core_dependency(source: str, core_url: str, core_ref: str) -> str:
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
    """Render the small README section that Core upgrades may safely replace."""

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
    """Update only the generator-owned Core dependency block, when present."""

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
    relative = str(path.relative_to(root))
    if path.exists():
        preserved.append(relative)
        return
    RunStore._atomic_text(path, content.rstrip("\n"))
    created.append(relative)


def scaffold_skills(root: Path) -> Dict[str, List[str]]:
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
    """Create the runtime-owned portion of a thin content workspace."""

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
        self.root = destination.resolve()

    def create(
        self,
        *,
        name: str,
        author_name: str,
        voice_id: Optional[str] = None,
        voice_label: Optional[str] = None,
        packs: Optional[Iterable[str]] = None,
        agent_template: str = STANDARD_TEMPLATE,
        core_source: str = DEFAULT_CORE_SOURCE,
        core_url: str = DEFAULT_CORE_URL,
        core_ref: str = DEFAULT_CORE_REF,
        perspective_mode: str = "automatic",
    ) -> Dict[str, Any]:
        if self.root.exists() and not self.root.is_dir():
            raise ValueError("Workspace destination is not a directory: {}".format(self.root))
        self.root.mkdir(parents=True, exist_ok=True)

        display_name = name.strip()
        author = author_name.strip()
        if not display_name:
            raise ValueError("Workspace name cannot be empty")
        if not author:
            raise ValueError("Author name cannot be empty")
        if perspective_mode not in {"automatic", "explicit", "disabled"}:
            raise ValueError("Perspective mode must be automatic, explicit, or disabled")

        label = (voice_label or "{} — General".format(author)).strip()
        resolved_voice_id = slugify(voice_id or label)
        if voice_id and resolved_voice_id != voice_id:
            raise ValueError("--voice-id must already be a repository-safe slug")

        selected_packs = list(dict.fromkeys(packs or DEFAULT_PACKS))
        available = {item.id for item in PackRegistry(self.root).list()}
        unknown = sorted(set(selected_packs) - available)
        if unknown:
            raise ValueError("Unknown content packs: {}".format(", ".join(unknown)))

        base_paths = (
            self.root / "profiles" / "registry.json",
            self.root / "content-creator.yaml",
        )
        base_path_existed = {path: path.exists() for path in base_paths}
        base = initialise_workspace(
            self.root,
            agent_template=agent_template,
            perspective_mode=perspective_mode,
        )
        if not base_path_existed[self.root / "content-creator.yaml"]:
            workspace_configuration = yaml.safe_load(
                (self.root / "content-creator.yaml").read_text(encoding="utf-8")
            )
            workspace_configuration["coordinator"]["default_voice"] = resolved_voice_id
            workspace_configuration["coordinator"]["default_pack"] = selected_packs[0]
            RunStore._atomic_text(
                self.root / "content-creator.yaml",
                yaml.safe_dump(workspace_configuration, sort_keys=False),
            )
        created: List[str] = []
        preserved: List[str] = []
        for item in base["agents"]["created"]:
            created.append(item if item.startswith("learnings/") else "agents/{}".format(item))
        for item in base["agents"]["preserved"]:
            preserved.append(item if item.startswith("learnings/") else "agents/{}".format(item))
        created.extend(base["skills"]["created"])
        preserved.extend(base["skills"]["preserved"])
        for path in base_paths:
            relative = str(path.relative_to(self.root))
            if base_path_existed[path]:
                preserved.append(relative)
            else:
                created.append(relative)

        package_name = slugify(display_name)
        dependency = core_dependency(core_source, core_url, core_ref)
        intended_uses = "\n".join("  --use {} \\".format(pack) for pack in selected_packs).rstrip(
            " \\"
        )

        _write_if_missing(
            self.root,
            self.root / "pyproject.toml",
            self._pyproject(package_name, display_name, author, dependency),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / ".gitignore",
            self._gitignore(),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / ".env.example",
            self._environment(),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / "AGENTS.md",
            self._agents_guidance(display_name, author, resolved_voice_id),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / "CLAUDE.md",
            self._claude_guidance(),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / "README.md",
            self._readme(
                display_name=display_name,
                author_name=author,
                voice_id=resolved_voice_id,
                voice_label=label,
                packs=selected_packs,
                core_ref=core_ref,
                dependency=dependency,
                intended_uses=intended_uses,
            ),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / "profiles" / resolved_voice_id / "learnings" / "memory.json",
            json.dumps({"version": 1, "records": []}, indent=2),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / "profiles" / resolved_voice_id / "onboarding.json",
            json.dumps(
                {
                    "schema_version": "1.0",
                    "voice_id": resolved_voice_id,
                    "display_name": label,
                    "author_name": author,
                    "status": "undecided",
                    "strategy": None,
                    "template_id": None,
                    "selected_by": None,
                    "selected_at": None,
                    "perspective_mode": "pending",
                    "perspective_disabled_reason": None,
                },
                indent=2,
            ),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / "voice-material" / resolved_voice_id / "source-urls.txt",
            (
                "# Add one authorised public source URL per line.\n"
                "# Local Markdown, text, DOCX, PDF, and HTML files may be placed\n"
                "# in this directory and supplied with --documents."
            ),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root / "tests" / "test_workspace.py",
            self._smoke_test(resolved_voice_id, selected_packs),
            created,
            preserved,
        )
        for pack in selected_packs:
            _write_if_missing(
                self.root,
                self.root / "content" / pack / "published" / ".gitkeep",
                "",
                created,
                preserved,
            )

        created = sorted(dict.fromkeys(created))
        preserved = sorted(dict.fromkeys(preserved))
        return {
            "status": "ok",
            "workspace": str(self.root),
            "name": display_name,
            "author_name": author,
            "voice_id": resolved_voice_id,
            "voice_label": label,
            "packs": selected_packs,
            "core_dependency": dependency,
            "perspective_mode": perspective_mode,
            "created": created,
            "preserved": preserved,
            "next_steps": [
                "cd {}".format(self.root),
                "uv sync --dev",
                "uv run content-creator --workspace . doctor",
                (
                    "Open the README and choose the source-derived or starter voice route for {}."
                ).format(resolved_voice_id),
            ],
        }
