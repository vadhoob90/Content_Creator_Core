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

DEFAULT_CORE_URL = "https://github.com/vadhoob90/Content_Creator_Core.git"
DEFAULT_CORE_REF = "v{}".format(VERSION)
DEFAULT_CORE_SOURCE = "registry"
DEFAULT_PACKS = ["general-text"]
VERSION_TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


def core_dependency(source: str, core_url: str, core_ref: str) -> str:
    if source == "registry":
        match = VERSION_TAG.fullmatch(core_ref)
        if not match:
            raise ValueError(
                "Registry dependencies require an immutable semantic version tag"
            )
        return "content-creator=={}".format(match.group("version"))
    if source == "git":
        return "content-creator @ git+{}@{}".format(
            core_url.rstrip("/"),
            core_ref,
        )
    raise ValueError("Core source must be registry or git")


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


class WorkspaceScaffolder:
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
            raise ValueError(
                "Workspace destination is not a directory: {}".format(self.root)
            )
        self.root.mkdir(parents=True, exist_ok=True)

        display_name = name.strip()
        author = author_name.strip()
        if not display_name:
            raise ValueError("Workspace name cannot be empty")
        if not author:
            raise ValueError("Author name cannot be empty")
        if perspective_mode not in {"automatic", "explicit", "disabled"}:
            raise ValueError(
                "Perspective mode must be automatic, explicit, or disabled"
            )

        label = (voice_label or "{} — General".format(author)).strip()
        resolved_voice_id = slugify(voice_id or label)
        if voice_id and resolved_voice_id != voice_id:
            raise ValueError("--voice-id must already be a repository-safe slug")

        selected_packs = list(dict.fromkeys(packs or DEFAULT_PACKS))
        available = {
            item.id for item in PackRegistry(self.root).list()
        }
        unknown = sorted(set(selected_packs) - available)
        if unknown:
            raise ValueError(
                "Unknown content packs: {}".format(", ".join(unknown))
            )

        base_paths = (
            self.root / "profiles" / "registry.json",
            self.root / "content-creator.yaml",
        )
        base_path_existed = {
            path: path.exists() for path in base_paths
        }
        base = initialise_workspace(
            self.root,
            agent_template=agent_template,
            perspective_mode=perspective_mode,
        )
        if not base_path_existed[self.root / "content-creator.yaml"]:
            workspace_configuration = yaml.safe_load(
                (self.root / "content-creator.yaml").read_text(
                    encoding="utf-8"
                )
            )
            workspace_configuration["coordinator"]["default_voice"] = (
                resolved_voice_id
            )
            workspace_configuration["coordinator"]["default_pack"] = (
                selected_packs[0]
            )
            RunStore._atomic_text(
                self.root / "content-creator.yaml",
                yaml.safe_dump(workspace_configuration, sort_keys=False),
            )
        created: List[str] = []
        preserved: List[str] = []
        for item in base["agents"]["created"]:
            created.append(
                item
                if item.startswith("learnings/")
                else "agents/{}".format(item)
            )
        for item in base["agents"]["preserved"]:
            preserved.append(
                item
                if item.startswith("learnings/")
                else "agents/{}".format(item)
            )
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
        intended_uses = "\n".join(
            "  --use {} \\".format(pack) for pack in selected_packs
        ).rstrip(" \\")

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
                intended_uses=intended_uses,
            ),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root
            / "profiles"
            / resolved_voice_id
            / "learnings"
            / "memory.json",
            json.dumps({"version": 1, "records": []}, indent=2),
            created,
            preserved,
        )
        _write_if_missing(
            self.root,
            self.root
            / "profiles"
            / resolved_voice_id
            / "onboarding.json",
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
            self.root
            / "voice-material"
            / resolved_voice_id
            / "source-urls.txt",
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
                    "Open the README and choose the source-derived or starter "
                    "voice route for {}."
                ).format(resolved_voice_id),
            ],
        }

    @staticmethod
    def _pyproject(
        package_name: str,
        display_name: str,
        author_name: str,
        dependency: str,
    ) -> str:
        return """[project]
name = {package_name}
version = "0.1.0"
description = {description}
readme = "README.md"
requires-python = ">=3.9"
dependencies = [
  {dependency},
]

[tool.uv]
package = false

[dependency-groups]
dev = [
  "pytest>=8,<9",
  "ruff>=0.9",
]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["UP006", "UP032", "UP035", "UP045"]
""".format(
            package_name=json.dumps(package_name),
            description=json.dumps(
                "{} content workspace for {}".format(display_name, author_name)
            ),
            dependency=json.dumps(dependency),
        )

    @staticmethod
    def _gitignore() -> str:
        return """__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.coverage
.venv/
dist/
build/
.env
outputs/
runs/
.eval-results/
.voice-cache/
profiles/*/work-order.json
voice-material/**/*
!voice-material/**/
!voice-material/**/source-urls.txt
content/*/drafting/
"""

    @staticmethod
    def _environment() -> str:
        return """# Choose a native subscription-backed provider where available:
CONTENT_CREATOR_PROVIDER=codex-native

# API providers require the corresponding optional dependency and key:
# CONTENT_CREATOR_PROVIDER=openai
# OPENAI_API_KEY=
# CONTENT_CREATOR_PROVIDER=anthropic
# ANTHROPIC_API_KEY=
"""

    @staticmethod
    def _agents_guidance(
        display_name: str,
        author_name: str,
        voice_id: str,
    ) -> str:
        return """# {display_name} repository guidance

This is a thin downstream Content Creator workspace for {author_name}.
Reusable mechanisms belong in `vadhoob90/Content_Creator_Core`; author-specific
voices, perspectives, sources, learnings, agents, content, and run artifacts
belong here.

## Content requests

Treat natural requests to create or revise supported content as an invocation
of the installed Content Creator workflow.

1. Run `content-creator --workspace . start` and use the next action derived
   from Core's persisted workspace state rather than chat memory.
2. Read `profiles/{voice_id}/onboarding.json`.
3. If its status is `undecided`, stop and ask the author to choose:
   build a source-derived voice from their writing, or use the neutral starter.
   Never choose on their behalf.
4. For the starter route, run `voice onboard --strategy starter`. Treat it as
   a neutral writing policy, never as the author's established voice.
   Perspectives are disabled by Core while it is active.
5. For the source-derived route, run `voice onboard --strategy source-derived`,
   collect authorised sources, and complete review and activation.
6. Create or validate a work order and resolve the pack and research route.
7. Use only an active, verified voice; the intended voice is `{voice_id}`.
8. Load only permitted voice learnings and perspectives.
9. Preserve generated artifacts under `runs/<run-id>/`.
10. Use `coordinator next-actions <run-id>` before offering an approval or
    publication action.
11. Return the final draft for author review.

An instruction to move the active draft into its published directory is author
approval for repository-local publication and learning extraction. It does not
authorise posting externally.

Do not invent sources, personal context, organisational claims, or
measurements. Do not commit, push, or publish externally unless explicitly
requested.
""".format(
            display_name=display_name,
            author_name=author_name,
            voice_id=voice_id,
        )

    @staticmethod
    def _claude_guidance() -> str:
        return """# Claude repository guidance

Read and follow `AGENTS.md`. It contains the canonical repository workflow,
ownership boundaries, approval trigger, and content-integrity rules.
"""

    @staticmethod
    def _readme(
        *,
        display_name: str,
        author_name: str,
        voice_id: str,
        voice_label: str,
        packs: List[str],
        core_ref: str,
        intended_uses: str,
    ) -> str:
        pack_list = "\n".join("- `{}`".format(pack) for pack in packs)
        return """# {display_name}

This is {author_name}'s thin Content Creator workspace. It owns the mutable
editorial material: authorised voice sources, voice-scoped learning,
perspectives, repository agents, drafts, and approved publications.

Reusable routing, provider adapters, schemas, validation, versioning, content
packs, and workflow contracts come from
[`Content_Creator_Core`](https://github.com/vadhoob90/Content_Creator_Core),
pinned at `{core_ref}`.

## Included content packs

{pack_list}

## Set up

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
uv sync --dev
uv run content-creator --workspace . doctor
uv run content-creator --workspace . overview
uv run pytest
```

For subscription-backed Codex:

```bash
codex login
uv run content-creator --workspace . provider select codex-native
uv run content-creator --workspace . provider verify codex-native
```

For Claude Code, authenticate and select `claude-native` instead. Core has no
implicit provider default: the workspace records this choice so opening a new
terminal cannot silently switch to a metered API provider.

## Choose how to begin

Run the guided entry point:

```bash
uv run content-creator --workspace . start
```

Before creating content, choose one voice route. If you are using chat, the
assistant must ask this question when onboarding is still undecided:

```text
Do you want to build a personalised voice from writing you can provide, or
begin with the neutral Clear Professional Starter?
```

The starter is a writing policy, not a representation of {author_name}'s
established voice. It cannot invent experience, identity, opinions, or
perspectives.

### Route A: build a voice from previous writing

Record the choice:

```bash
uv run content-creator --workspace . voice onboard {voice_id} \\
  --strategy source-derived \\
  --author-name "{author_name}" \\
  --label "{voice_label}" \\
  --selected-by "{author_name}" \\
{intended_uses}
```

If you already have writing on this computer, point Core directly at its
directory. The files may remain outside this Git repository and are read in
place; supported files are discovered recursively:

```bash
uv run content-creator --workspace . voice add-sources {voice_id} \\
  --documents "/absolute/path/to/my-writing"
```

Core does not copy those originals into the repository. Private filesystem
paths remain in the ignored operational work order and cache; versioned voice
artifacts retain only `local-document:<filename>` references and content
hashes.

For authorised public sources, add URLs to
`voice-material/{voice_id}/source-urls.txt` and run:

```bash
uv run content-creator --workspace . voice add-sources {voice_id} \\
  --sources voice-material/{voice_id}/source-urls.txt
```

Build the candidate:

```bash
uv run content-creator --workspace . voice build {voice_id}
```

Review and approve it:

```bash
uv run content-creator --workspace . voice status {voice_id}
uv run content-creator --workspace . voice show {voice_id}
uv run content-creator --workspace . voice verify {voice_id}
uv run content-creator --workspace . voice approve {voice_id} \\
  --approved-by "{author_name}"
```

### Route B: begin without previous writing

Activate the neutral starter:

```bash
uv run content-creator --workspace . voice onboard {voice_id} \\
  --strategy starter \\
  --author-name "{author_name}" \\
  --label "{voice_label}" \\
  --selected-by "{author_name}" \\
{intended_uses}
```

This activates a versioned starter profile and automatically disables
perspective creation, selection, and extraction for that voice. Runs record
that no author evidence was used.

When approved writing becomes available, repeat Route A. The starter remains
usable while the candidate is reviewed. Activating the source-derived version
re-enables the workspace's normal perspective policy.

## Create content using chat

Open this repository in Codex or Claude Code and describe the content in
ordinary language:

```text
Write a useful piece for my professional audience. Use no external research.
```

Repository guidance tells the chat to invoke Content Creator, resolve the
selected pack and active voice, preserve the run artifacts, and return the
draft for review.

To approve repository-local publication, say:

```text
Move the active draft into the published directory.
```

This does not post to an external platform.

## Create content using the CLI

Preview Core's proposed decisions without creating a run:

```bash
uv run content-creator --workspace . start \\
  "Write a useful piece for my professional audience"
```

Then create the reviewed route explicitly:

```bash
uv run content-creator --workspace . run \\
  "Write a useful piece for my professional audience" \\
  --pack {first_pack} \\
  --voice {voice_id} \\
  --research none \\
  --provider codex-native
```

## Ownership boundary

Change author-specific agents, voices, sources, learnings, perspectives,
content, and tests here. Add reusable mechanisms to Content Creator Core and
upgrade the pinned dependency deliberately.

Do not copy `src/content_creator`, core contracts, provider adapters, or
packaged resources into this repository.
""".format(
            display_name=display_name,
            author_name=author_name,
            core_ref=core_ref,
            pack_list=pack_list,
            voice_id=voice_id,
            voice_label=voice_label,
            intended_uses=intended_uses,
            first_pack=packs[0],
        )

    @staticmethod
    def _smoke_test(voice_id: str, packs: List[str]) -> str:
        return """import json
from pathlib import Path

from content_creator.cli import main


ROOT = Path(__file__).resolve().parents[1]


def test_thin_workspace_resolves_packaged_core(capsys):
    assert main(["--workspace", str(ROOT), "doctor"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "ok"
    assert result["checks"]["repository_agents"]["complete"] is True
    assert {packs!r} <= set(result["checks"]["content_packs"])


def test_voice_workspace_is_scoped_to_expected_author():
    assert (ROOT / "voice-material" / {voice_id!r}).is_dir()
    memory = json.loads(
        (
            ROOT
            / "profiles"
            / {voice_id!r}
            / "learnings"
            / "memory.json"
        ).read_text(encoding="utf-8")
    )
    assert memory == {{"version": 1, "records": []}}
""".format(
            voice_id=voice_id,
            packs=set(packs),
        )
