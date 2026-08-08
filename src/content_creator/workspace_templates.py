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


AUTHOR_WORKSPACE_README_TEMPLATE = """# {display_name}

This is {author_name}'s Content Creator workspace. It keeps your voice,
perspectives, editorial agents, feedback-derived learning, drafts, and approved
content together without publishing anything externally.

## Quick start

Open this folder in Codex or Claude Code and describe what you want to create:

```text
Write a useful piece for my professional audience. Use no external research.
```

The assistant will inspect the workspace, select only an active voice and
approved perspectives, apply previous feedback, and return a draft for review.
To approve a repository-local copy, say:

```text
Move the active draft into the published directory.
```

## Understand your workspace

- [How this system is personalised to me](PERSONALISATION.md)
- [My agents](agents/README.md)
- [My voices and perspectives](profiles/README.md)
- [My shared learning](learnings/README.md)
- [What my agents receive at runtime](docs/runtime-context.md)
- [My approved content](content/)
- [Technical setup, uv, providers, and CLI usage](docs/setup-and-technical-guide.md)

The guided personalisation view is also available as:

```bash
content-creator --workspace . personalisation show
```

## Included content packs

{pack_list}

## First-time voice choice

Before creating content, the assistant will ask whether to build a personalised
voice from writing you provide or begin with the neutral Clear Professional
Starter. It must not choose for you. Your intended voice is `{voice_id}`
(`{voice_label}`).

The starter is a writing policy, not a representation of {author_name}'s
established voice. It cannot invent experience, identity, opinions, or
perspectives.

## Technical users

Terminal installation and maintenance use `uv`, but they are not required to
understand or navigate this workspace. See the
[technical setup guide](docs/setup-and-technical-guide.md) for the complete
commands.

{core_dependency_section}

## Ownership

Your agents, voice material, learnings, perspectives, content, and tests belong
in this repository. Reusable workflow mechanisms come from
[`Content_Creator_Core`](https://github.com/vadhoob90/Content_Creator_Core).
"""


PERSONALISATION_TEMPLATE = """# How this system is personalised to me

This page is the starting point for understanding how Content Creator represents
{author_name}. Live state always comes from Core's manifests, registries, and
receipts rather than this explanatory page.

Run `content-creator --workspace . personalisation show` for the current
human-readable view, or add `--json` for structured output.

Use [`docs/runtime-context.md`](docs/runtime-context.md) to preview the exact
sources a role would receive, watch a live loading trace, or inspect a completed
run.

## My agents

Open [`agents/README.md`](agents/README.md) to see what each agent does. The live
view identifies which agent files are customised and which remain unchanged Core
starting points. An agent's effective instructions combine its Core contract,
repository file, active voice, selected perspectives, role-matched learning,
rubrics, and pack instructions.

## What my agents have learnt

- [`learnings/memory.json`](learnings/memory.json) contains policies shared by
  every voice in this workspace.
- [`profiles/{voice_id}/learnings/memory.json`](profiles/{voice_id}/learnings/memory.json)
  contains learning belonging only to `{voice_id}`.

Only active records matching the executing role reach an agent. Provisional and
rejected records remain inspectable but do not enter prompts.

## My voice and perspectives

- [`profiles/registry.json`](profiles/registry.json) selects active voices.
- [`profiles/{voice_id}/`](profiles/{voice_id}/) contains the intended voice,
  immutable versions, candidate decisions, learning, and perspectives.
- [`profiles/{voice_id}/perspectives/`](profiles/{voice_id}/perspectives/) contains
  separately governed author positions.

Candidate and active lifecycle state comes from manifests and decision receipts.
Profile prose is evidence and guidance, not lifecycle authority.
"""


PROFILES_README_TEMPLATE = """# Voices and perspectives

The registry in [`registry.json`](registry.json) selects the active immutable
voice version. Each voice directory contains its evidence, versions, incremental
learning, and separately approved perspective contexts.

Start with [`{voice_id}/README.md`]({voice_id}/README.md), or run
`content-creator --workspace . personalisation show` for current state and valid
decisions.
"""


VOICE_README_TEMPLATE = """# {voice_label}

This directory contains the voice `{voice_id}`.

- `versions/` contains immutable approved voice versions.
- `candidate/` contains a candidate awaiting a decision, when present.
- `rejections/` preserves rejected candidate evidence and receipts.
- `learnings/memory.json` contains active, provisional, and rejected learning.
- `perspectives/` contains context-specific author positions.

Use `content-creator --workspace . personalisation show` for authoritative
current state. Do not infer lifecycle state from historical profile prose.
"""


LEARNINGS_README_TEMPLATE = """# Shared learning

`memory.json` contains learning that applies to every voice in this repository.
Voice-specific feedback belongs under `profiles/<voice-id>/learnings/memory.json`.

Learning is role-specific. Only active records for the executing `writer`,
`researcher`, or `critic` enter that agent's prompt. Provisional and rejected
records remain visible for review but are not applied.

Run `content-creator --workspace . personalisation show` to read the active
principles in plain language.
"""


TECHNICAL_SETUP_TEMPLATE = """# Technical setup and command-line usage

Most authors can work conversationally by opening the repository in Codex or
Claude Code. This page is for maintainers who install dependencies, select a
provider, run checks, or upgrade Core.

## Install and verify

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
uv sync --dev
uv run content-creator --workspace . doctor
uv run content-creator --workspace . overview
uv run content-creator --workspace . personalisation show
uv run content-creator --workspace . personalisation explain --role writer
uv run pytest
```

For subscription-backed Codex:

```bash
codex login
uv run content-creator --workspace . provider select codex-native
uv run content-creator --workspace . provider verify codex-native
```

For Claude Code, authenticate and select `claude-native` instead. Core has no
implicit provider default.

## Voice onboarding

Run `uv run content-creator --workspace . start` for the guided route. Source
material may remain outside this repository and be supplied with the
`voice add-sources` command and its `--documents` option. Review candidate
status and the copyable approval or rejection commands with
`personalisation show`.

## Direct content creation

```bash
uv run content-creator --workspace . start \\
  "Write a useful piece for my professional audience"

uv run content-creator --workspace . run \\
  "Write a useful piece for my professional audience" \\
  --pack {first_pack} \\
  --voice {voice_id} \\
  --research none \\
  --provider codex-native
```

Core never publishes externally. The `publish` command writes only an approved
copy inside this repository.
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
        return AUTHOR_WORKSPACE_README_TEMPLATE.format(
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
