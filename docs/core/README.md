# Working on Content Creator Core

This guide is for developers who want to inspect or change the reusable Content
Creator engine. If you want to create content for a person, generate a
[thin workspace](../guides/creating-a-content-workspace.md) instead.

## Clone and install

Content Creator requires Python 3.11 or newer. Clone the repository and install
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
├── linguistics.py        deterministic voice measurements and statistics
├── voice_assessment.py   advisory draft-to-voice scoring
├── voice_ml.py           optional local ML training and inference
├── perspectives.py       perspective provenance and resolution
├── diagnostics.py        local runtime diagnostic journal and summaries
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
ruff format --check .
mypy
pytest --cov=content_creator --cov-report=term-missing
content-creator doctor
content-creator eval
git diff --check
```

The complete quality, compatibility, security, and release baseline is defined
in the [Core engineering standards](engineering-standards.md).

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

Changes to linguistic measurement should additionally test deterministic
feature extraction, attribution weighting, spoken/written separation,
distribution summaries, and empty or insufficient corpora. The [statistical
voice evidence guide](../guides/linguistic-voice-framework.md) documents the
public interpretation limits that implementation changes must preserve.

## Providers and live evaluation

Core supports subscription-backed native adapters and API adapters. Normal
development should use offline fakes and replay cases.

For an authenticated native smoke test:

```bash
codex login
content-creator provider select codex-native
content-creator provider verify codex-native
```

Or:

```bash
claude auth login
content-creator provider select claude-native
content-creator provider verify claude-native
```

API providers require the relevant optional dependency and credential:

```bash
python -m pip install -e ".[providers,dev]"
content-creator provider select openai
export OPENAI_API_KEY="<key>"
content-creator provider verify openai
```

Core deliberately ships without a provider default. Select one in
`content-creator.yaml`, pass `--provider`, or set
`CONTENT_CREATOR_PROVIDER` for a temporary shell override. This prevents a
missing environment variable from silently changing a native workflow into a
metered API workflow.

Never make a paid live-provider call merely to validate deterministic logic.

## Release and downstream verification

Merging a change into `main` does not publish it. Create a release only when a
reviewed set of changes should become available to author workspaces.
Documentation-only and internal maintenance changes can remain unreleased.

PyPI releases and their corresponding Git tags are immutable. Every public
release therefore needs a new semantic version:

- increment the patch version for a backward-compatible fix;
- increment the minor version for backward-compatible functionality; and
- increment the major version for an incompatible change.

The project is currently below `1.0.0`, but release notes must still call out
any migration required by a minor release.

### Prepare the release

1. Create a branch from current `main`.
2. Choose the next version and update it in both `pyproject.toml` and
   `src/content_creator/version.py`.
3. Move the completed entries under `Unreleased` in `CHANGELOG.md` into a
   dated version section.
4. Confirm that installation, migration, and compatibility documentation
   reflects the release.
5. Run:

   ```bash
   uv run ruff check .
   uv run pytest
   uv run content-creator --workspace . doctor
   uv run content-creator --workspace . eval
   git diff --check
   ```

6. For workspace-generator changes, generate a temporary author workspace,
   run doctor and its generated tests, and verify that running the generator
   again preserves repository-owned files.
7. Open a pull request, wait for all required checks, and merge it into
   protected `main`.

The package workflow performs an additional clean-wheel installation and
generated-workspace test. Local checks must still pass before the release
commit reaches `main`.

### Publish the release

Create the matching annotated tag only after the release PR is merged. For
example, for `0.11.0`:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.11.0 -m "Content Creator 0.11.0"
git push origin v0.11.0
```

Pushing the tag triggers `.github/workflows/release.yml`. The workflow:

1. rejects a tag that does not match the package version;
2. builds and validates the wheel and source distribution;
3. checks packaged contracts, packs, profiles, skills, templates, metadata,
   licences, and hashes;
4. installs the wheel in a clean environment and tests a generated workspace;
5. publishes to PyPI through the `pypi` environment using Trusted Publishing;
   and
6. creates a GitHub release containing the distributions, manifest, and
   checksums.

Trusted Publisher registration is a one-time repository setup. Maintainers do
not create or copy a PyPI API token for each release. Do not manually create
the GitHub release before the workflow runs, and never move or reuse a tag
after its package has been published. If a release is defective, yank it on
PyPI when appropriate and publish a corrected patch version.

Verify the completed release on:

- `https://pypi.org/project/content-creator/<version>/`
- `https://github.com/vadhoob90/Content_Creator_Core/releases/tag/v<version>`

### Upgrade author workspaces

Author workspaces remain on their pinned package until deliberately upgraded.
Preview the upgrade first:

```bash
uv run content-creator --workspace . workspace upgrade --to v0.11.0
```

Apply the reviewed preview explicitly:

```bash
uv run content-creator --workspace . workspace upgrade --to v0.11.0 --apply
```

The apply operation updates the package requirement and lockfile, runs doctor,
verifies all voices, runs workspace tests, and restores the previous
dependency, lockfile, and managed README dependency block if validation fails.
It never rewrites the rest of the README, and leaves legacy or custom READMEs
without that marker unchanged. Review and commit the resulting
`pyproject.toml`, `uv.lock`, `README.md` when updated, and any deliberately
scaffolded files through a pull request in each consumer repository.

Do not make production consumers follow the moving `main` branch or use an
unpinned package version.

## Further technical guides

- [Core engineering standards](engineering-standards.md)
- [How voice is derived](../guides/how-voice-is-derived.md)
- [Statistical voice evidence](../guides/linguistic-voice-framework.md)
- [Voice onboarding](../guides/voice-onboarding.md)
- [Perspective provenance](../guides/perspective-provenance.md)
- [Repository-owned agents](../guides/repository-agents.md)
- [Provider configuration](../guides/provider-configuration.md)
- [Versioned workspaces](../guides/workspace-dependencies.md)
- [Migrating to v0.4](../guides/migrating-to-v0.4.md)
- [Changelog](../../CHANGELOG.md)
- [Delivery plan](../work-package/delivery-plan.md)
- [Testing and acceptance](../work-package/testing-and-acceptance.md)

External code contributions are not currently accepted. Read the repository
[contribution policy](../../CONTRIBUTING.md) before opening an issue or
proposing a change.
