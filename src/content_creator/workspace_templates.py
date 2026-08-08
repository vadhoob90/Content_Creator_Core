"""Provide workspace templates capabilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List

DEFAULT_CORE_URL = "https://github.com/vadhoob90/Content_Creator_Core.git"
README_CORE_START = "<!-- content-creator-core-dependency:start -->"
README_CORE_END = "<!-- content-creator-core-dependency:end -->"


def readme_core_dependency(core_ref: str, dependency: str) -> str:
    """Return the readme core dependency.

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


@dataclass(frozen=True)
class WorkspaceReadmeContext:
    """Represent a workspace readme context."""

    display_name: str
    author_name: str
    voice_id: str
    voice_label: str
    packs: List[str]
    core_ref: str
    dependency: str
    intended_uses: str


WORKSPACE_README_TEMPLATE = """# {display_name}

This is {author_name}'s thin Content Creator workspace. It owns the mutable
editorial material: authorised voice sources, voice-scoped learning,
perspectives, repository agents, drafts, and approved publications.

Reusable routing, provider adapters, schemas, validation, versioning, content
packs, and workflow contracts come from
[`Content_Creator_Core`](https://github.com/vadhoob90/Content_Creator_Core).

{core_dependency_section}

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
"""


class WorkspaceTemplates:
    """Render files for a newly scaffolded workspace."""

    @staticmethod
    def _pyproject(
        package_name: str,
        display_name: str,
        author_name: str,
        dependency: str,
    ) -> str:
        """Return the pyproject.

        Render the generated workspace package metadata, dependency pin, development extras,
        and command entry points.

        Args:
            package_name (str): The package name text processed when pyproject.
            display_name (str): The human-readable name shown to users.
            author_name (str): The author's display name.
            dependency (str): The pinned Core dependency declaration.

        Returns:
            str: The resulting text for pyproject.
        """
        return """[project]
name = {package_name}
version = "0.1.0"
description = {description}
readme = "README.md"
requires-python = ">=3.11"
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
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["UP006", "UP032", "UP035", "UP045"]
""".format(
            package_name=json.dumps(package_name),
            description=json.dumps("{} content workspace for {}".format(display_name, author_name)),
            dependency=json.dumps(dependency),
        )

    @staticmethod
    def _gitignore() -> str:
        """Return the gitignore.

        Returns:
            str: The resulting text for gitignore.
        """
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
.content-creator/
.voice-cache/
profiles/*/work-order.json
voice-material/**/*
!voice-material/**/
!voice-material/**/source-urls.txt
content/*/drafting/
"""

    @staticmethod
    def _environment() -> str:
        """Return the environment.

        Returns:
            str: The resulting text for environment.
        """
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
        """Return the agents guidance.

        Render repository guidance that constrains content agents, approval behavior,
        learning scope, and publication safety.

        Args:
            display_name (str): The human-readable name shown to users.
            author_name (str): The author's display name.
            voice_id (str): The stable identifier for the selected voice.

        Returns:
            str: The resulting text for agents guidance.
        """
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

When an exact invocation may be retried, reuse one stable `--idempotency-key`
for that submission or inspect it with `submission status <key>`. Changed
instructions and deliberate revisions require a new key. Revisions also pass
`--parent-run <run-id>` to preserve content lineage.

An instruction to move the active draft into its published directory is author
approval for repository-local publication and learning extraction. It does not
authorise posting externally.

Successful publication writes a privacy-safe receipt under
`publication-receipts/`. Run `verify-publications` before committing published
content or receipt changes. Treat an enforced finding as a publication
integrity failure; the verifier is offline and must not invoke a model.

If publication returns `review_required`, present the finding codes and the
ignored semantic-review artifact. The author may revise the draft or repeat
publication with `--perspective-review-approved-by "<reviewer>"` after reviewing
the unchanged draft. Never select this approval for the author; model findings
may pause publication but cannot approve or reject it.

When durable author feedback arrives after publication, or on a reviewed draft
that should remain unpublished, use `learn <run-id> --feedback "..."
--idempotency-key <stable-key>`. This updates only the run's verified voice
learning memory and never writes to a content pack destination.

Recovered operational diagnostics stay deferred throughout normal draft
iterations. If publication returns `awaiting_diagnostic_decision`, present the
sanitised Core support candidate once and ask whether to publish only or
publish and prepare an issue. Surface fatal Core diagnostics immediately.
Never create an external issue without explicit approval.

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
        """Return the claude guidance.

        Returns:
            str: The resulting text for claude guidance.
        """
        return """# Claude repository guidance

Read and follow `AGENTS.md`. It contains the canonical repository workflow,
ownership boundaries, approval trigger, and content-integrity rules.
"""

    @staticmethod
    def _readme(context: WorkspaceReadmeContext) -> str:
        """Return the readme.

        Args:
            context (WorkspaceReadmeContext): The operation context and its resolved
                dependencies.

        Returns:
            str: The resulting text for readme.
        """
        pack_list = "\n".join("- `{}`".format(pack) for pack in context.packs)
        return WORKSPACE_README_TEMPLATE.format(
            display_name=context.display_name,
            author_name=context.author_name,
            core_dependency_section=readme_core_dependency(context.core_ref, context.dependency),
            pack_list=pack_list,
            voice_id=context.voice_id,
            voice_label=context.voice_label,
            intended_uses=context.intended_uses,
            first_pack=context.packs[0],
        )

    @staticmethod
    def _smoke_test(voice_id: str, packs: List[str]) -> str:
        """Return the smoke test.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            packs (List[str]): The packs collection consumed while smoke test.

        Returns:
            str: The resulting text for smoke test.
        """
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
