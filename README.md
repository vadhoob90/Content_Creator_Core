# Content Creator

Content Creator helps a person create consistent, reviewable content in a thin,
author-owned workspace while reusable orchestration remains in Core.

The LLM supplies intelligence; the scaffolding supplies direction, memory,
boundaries and accountability.

ChatGPT and Claude already provide capable conversation, instructions, files,
and memory. Content Creator adds a provider-neutral publication workflow with
explicit voice provenance, scoped learning, immutable versions, research
checkpoints, and author approval. Read
[Why not just use ChatGPT or Claude?](docs/guides/why-not-just-chat.md).

## Create your content workspace

### Ask an AI coding assistant to set it up

If Codex, Claude Code, or another assistant can run terminal commands and write
files on your computer, paste this prompt:

> Use [Content Creator
> Core](https://github.com/vadhoob90/Content_Creator_Core) to create a new thin
> content workspace for me. Do not clone or copy the Core repository. Follow
> its workspace-creation guide, ask me only for the author and content choices
> you need, generate the workspace locally, install its dependencies, and run
> its validation tests.

The assistant should guide you through the workspace location, author identity,
content packs, provider, and starter versus source-derived voice decision. A
regular chat session without terminal and filesystem access can explain the
commands but cannot create the repository on your computer.

### Set it up from the terminal

Most people should not clone this repository. Install the immutable `v0.4.0`
Core release and generate a thin workspace:

```bash
uv tool install \
  "content-creator @ git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.4.0"

content-creator workspace create Content_Creator_Alice \
  --name "Content Creator Alice" \
  --author-name "Alice Example" \
  --voice-id alice-general \
  --pack linkedin-post \
  --pack linkedin-article \
  --core-ref v0.4.0
```

The generated repository owns Alice's voices, sources, perspectives, learning,
agents, drafts, tests, and publications. It pins Core rather than copying the
engine. Enter it and check the installation:

```bash
cd Content_Creator_Alice
uv sync --dev
uv run content-creator --workspace . doctor
uv run pytest
```

Select a provider deliberately. The choice is persisted in the workspace:

```bash
uv run content-creator --workspace . provider select codex-native
uv run content-creator --workspace . provider verify codex-native
```

See [Create a thin content workspace](docs/guides/creating-a-content-workspace.md)
for all options and the generated repository layout.

## First checkpoint: choose a voice route

The generated workspace begins with voice onboarding marked `undecided`. The
author—not the assistant—chooses one of two routes.

### Use previous writing

Choose this route when the author can provide documents, Markdown files, or
authorised URLs:

```bash
uv run content-creator --workspace . voice onboard alice-general \
  --strategy source-derived \
  --author-name "Alice Example" \
  --selected-by "Alice Example" \
  --use linkedin-post \
  --use linkedin-article
```

Point Core at an existing local directory. Files are read recursively in place;
they are not uploaded to GitHub or copied into the workspace:

```bash
uv run content-creator --workspace . voice add-sources alice-general \
  --documents "/absolute/path/to/my-writing"
uv run content-creator --workspace . voice build alice-general
uv run content-creator --workspace . voice show alice-general
uv run content-creator --workspace . voice verify alice-general
uv run content-creator --workspace . voice approve alice-general \
  --approved-by "Alice Example"
```

Public URLs may instead be listed in
`voice-material/alice-general/source-urls.txt`. Uploaded documents and local
work-order paths are ignored by Git; versioned artifacts retain privacy-safe
references and content hashes.

### Begin without previous writing

Choose the Clear Professional Starter:

```bash
uv run content-creator --workspace . voice onboard alice-general \
  --strategy starter \
  --author-name "Alice Example" \
  --selected-by "Alice Example" \
  --use linkedin-post \
  --use linkedin-article
```

The starter is a neutral writing policy, not a synthetic version of Alice's
personality, experience, opinions, or established voice. Core automatically
disables perspectives while it is active and records that no author evidence
was used.

Approved writing can later become evidence for a source-derived candidate.
Activating that candidate replaces the starter as the active version and
restores the workspace's normal perspective policy. Core never performs that
transition silently.

Read [Voice onboarding](docs/guides/voice-onboarding.md) for the lifecycle,
safeguards, and transition procedure. The detailed derivation algorithm is in
[How Content Creator derives a voice](docs/guides/how-voice-is-derived.md).

## Create content

Open the thin workspace in Codex or Claude Code and ask naturally:

> Write a short LinkedIn post explaining why calculus matters to sixth-form
> students. No external research is required.

The workspace guidance resolves the voice, pack, research route, evidence, and
approval points. It preserves the run artifacts and returns the draft for
review. It does not publish externally.

The equivalent CLI request is:

```bash
uv run content-creator --workspace . run \
  "Explain why calculus matters to sixth-form students" \
  --voice alice-general \
  --pack linkedin-post \
  --research none
```

After review, repository-local publication is explicit:

```bash
uv run content-creator --workspace . publish <run-id> \
  --feedback "Preserve the concrete opening."
```

Publication never overwrites an existing file and updates only that voice's
learning memory.

## How the system fits together

```mermaid
flowchart TD
    W["Generate thin workspace"] --> D{"Voice onboarding checkpoint"}
    D -->|"Previous writing"| VB["Voice Builder"]
    VB --> VC["Candidate voice"]
    VC --> VA["Author review and approval"]
    VA --> AV["Active source-derived voice"]
    D -->|"No previous writing"| SV["Clear Professional Starter"]
    SV --> PD["Perspectives disabled"]
    SV --> EW["Approved writing accumulates"]
    EW --> VB
    AV --> PE["Approved perspective catalogue"]

    R["Natural-language request"] --> BA["Briefing Agent"]
    BA --> OR["Orchestrator"]
    PK["Content pack"] --> OR
    AV --> OR
    SV --> OR
    PE --> OR
    OR --> CR["Capability router"]
    CR --> PR["OpenAI, Anthropic, Codex, Claude, or another adapter"]
    OR --> Q{"Research needed?"}
    Q -->|"No"| DR["Draft and review"]
    Q -->|"Yes"| RS["Research and checkpoint"]
    RS --> DR
    DR --> HA["Human approval"]
    HA --> PB["Repository publication"]
    PB --> LM["Voice-scoped learning"]
```

Every run records the exact content pack, voice strategy and version, allowed
perspectives, research state, agent instructions, and learning memories used.

## Learn more

- [Create a thin content workspace](docs/guides/creating-a-content-workspace.md)
- [Voice onboarding](docs/guides/voice-onboarding.md)
- [How voice is derived](docs/guides/how-voice-is-derived.md)
- [Perspective provenance](docs/guides/perspective-provenance.md)
- [Repository-owned agents](docs/guides/repository-agents.md)
- [Provider configuration](docs/guides/provider-configuration.md)
- [Versioned Core dependencies](docs/guides/workspace-dependencies.md)
- [Changelog](CHANGELOG.md)
- [Migrating to v0.4](docs/guides/migrating-to-v0.4.md)

## Work on Content Creator Core

Clone Core only when you want to understand or change the reusable engine,
provider adapters, contracts, validation, packaged resources, or workspace
generator.

The [Core development README](docs/core/README.md) explains how to clone,
install, navigate, test, modify, and validate this repository without confusing
Core-owned mechanisms with downstream editorial policy.

## Licence

Content Creator is free and open-source software licensed under the
[GNU Affero General Public License, version 3 or (at your option) any later
version](LICENSE.md) (`AGPL-3.0-or-later`).

Commercial use is permitted under the AGPL. If you modify the program and make
the modified version available for users to interact with remotely over a
network, the AGPL requires you to offer those users the corresponding source
code of that version. The licence text controls; see
[Licensing](LICENSING.md) for a plain-language overview.

External code contributions are not currently accepted. Bug reports and
feature requests are welcome through GitHub Issues; read
[Contributing](CONTRIBUTING.md) first.

Copyright © 2026 Bharath Vadhoola
