# Working on Content Creator Core

This guide is for developers who want to inspect or change the reusable Content
Creator engine. If you want to create content for a person, generate a
[thin workspace](../guides/creating-a-content-workspace.md) instead.

## Clone and install

Content Creator requires Python 3.9 or newer. Clone the repository and install
an editable development environment:

```bash
git clone https://github.com/vadhoob90/Content_Creator_Core.git
cd Content_Creator_Core
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Run the offline baseline:

```bash
content-creator init
content-creator doctor
content-creator eval
pytest
ruff check .
```

`doctor`, replay evaluation, and the test suite do not require paid model
calls. Live provider evaluation remains an explicit action.

## Understand the repository

```text
src/content_creator/
├── orchestrator.py       workflow execution and checkpoints
├── voices.py             voice lifecycle, activation, and onboarding
├── voice_builder.py      source-derived voice analysis
├── perspectives.py       perspective provenance and resolution
├── providers/            normalized provider adapters
├── workspace.py          thin-repository generator
└── resources/            packaged contracts, packs, rubrics, and defaults

agents/                   repository-editable agent starting points
contracts/                non-negotiable Core role contracts
packs/                    source copies of packaged content packs
profiles/                 source copies of packaged profiles
tests/                    offline behavioral and integration tests
docs/                     architecture, algorithms, guides, and work package
```

The runtime composes:

```text
Core harness and role contract
+ repository-owned agent instructions
+ repository and voice-scoped learning
+ active voice version
+ permitted perspective versions
+ content pack and research rubric
+ current work order
```

Repository instructions may specialise behavior but cannot remove Core
integrity boundaries.

## Core versus a thin workspace

Put a change in Core when it is reusable across authors, teams, or content
types:

- orchestration and lifecycle mechanics;
- provider interfaces and adapters;
- shared schemas and validation;
- voice, perspective, provenance, and learning boundaries;
- workspace generation;
- generic packs, rubrics, and role contracts; or
- deterministic evaluation and persistence.

Put a change in a thin workspace when it belongs to a particular author or
organisation:

- source material and voice evidence;
- approved perspectives;
- personal writing rules;
- editorial learning;
- domain agent specialisation;
- drafts, research, and publications; or
- private policies and tests.

Do not copy `src/content_creator` into a thin workspace. Pin a Core release and
upgrade it deliberately.

## Make a change

Start from the latest `main`, create a focused branch, and keep unrelated
workspace changes out of the commit:

```bash
git switch main
git pull --ff-only
git switch -c codex/short-description
```

When changing packaged resources, remember that repository source copies and
`src/content_creator/resources/` may intentionally mirror one another. The
resource parity tests identify required updates.

Use `content-creator --help` and the focused command help while developing:

```bash
content-creator workspace create --help
content-creator voice --help
content-creator perspective --help
content-creator run --help
```

## Validate proportionately

For a narrow Python change:

```bash
ruff check path/to/changed_file.py tests/test_relevant_area.py
pytest tests/test_relevant_area.py
```

Before proposing or publishing a Core change:

```bash
ruff check .
pytest
content-creator doctor
content-creator eval
git diff --check
```

Changes to the workspace generator should additionally create a temporary thin
workspace, inspect its generated README and configuration, run its smoke test,
and confirm that a second generation preserves custom files.

Changes to voices or perspectives should test:

- lifecycle transitions and idempotency;
- immutable version resolution and component hashes;
- unsupported personal claims;
- perspective isolation and provenance;
- run-level resolved context; and
- migration from previous manifests or workspace configuration.

## Providers and live evaluation

Core supports subscription-backed native adapters and API adapters. Normal
development should use offline fakes and replay cases.

For an authenticated native smoke test:

```bash
codex login
export CONTENT_CREATOR_PROVIDER=codex-native
content-creator provider verify codex-native
```

Or:

```bash
claude auth login
export CONTENT_CREATOR_PROVIDER=claude-native
content-creator provider verify claude-native
```

API providers require the relevant optional dependency and credential:

```bash
python -m pip install -e ".[providers,dev]"
export CONTENT_CREATOR_PROVIDER=openai
export OPENAI_API_KEY="<key>"
content-creator provider verify openai
```

Never make a paid live-provider call merely to validate deterministic logic.

## Release and downstream verification

Core consumers pin immutable tags or reviewed commits. A release change should
therefore be validated in this order:

1. Run Core lint, tests, doctor, and replay evaluation.
2. Update version and release documentation.
3. Tag the reviewed Core commit.
4. Update each downstream dependency and lockfile deliberately.
5. Run downstream doctor, voice verification, lint, and tests.
6. Review generated-workspace compatibility.

Do not make production consumers follow the moving `main` branch.

## Further technical guides

- [How voice is derived](../guides/how-voice-is-derived.md)
- [Voice onboarding](../guides/voice-onboarding.md)
- [Perspective provenance](../guides/perspective-provenance.md)
- [Repository-owned agents](../guides/repository-agents.md)
- [Provider configuration](../guides/provider-configuration.md)
- [Versioned workspaces](../guides/workspace-dependencies.md)
- [Delivery plan](../work-package/delivery-plan.md)
- [Testing and acceptance](../work-package/testing-and-acceptance.md)

External code contributions are not currently accepted. Read the repository
[contribution policy](../../CONTRIBUTING.md) before opening an issue or
proposing a change.
