# Content Creator

Content Creator helps people produce consistent, reviewable content without
giving an AI control of their identity, opinions, or publication decisions.

Each author works in a small, independent repository containing their voices,
agents, learning, drafts, and approved content. This Core repository supplies
the reusable workflow, validation, and safety boundaries.

Here, **voice** means the author's written communication style: observable
patterns in how they shape text. It is not a model of the whole person and does
not claim to capture their identity, personality, beliefs, expertise, or inner
character. Authorised transcripts may provide supporting evidence, but the
resulting voice guides text creation.

Read [Why not just use a chat app?](docs/guides/why-not-just-chat.md) for the
design rationale.

Content Creator Core is distributed through PyPI as
[`content-creator`](https://pypi.org/project/content-creator/). Author
workspaces pin an exact package version so installation and upgrades remain
reproducible.

## The quickest way to start

Give this request to Codex, Claude Code, or another coding assistant with
terminal and filesystem access:

> Use [Content Creator
> Core](https://github.com/vadhoob90/Content_Creator_Core) to create a thin
> content workspace for me. Do not clone or copy Core. Follow its
> workspace-creation guide, ask me for the author and content choices you
> need, install the workspace, and validate it.

The assistant will ask about the author, intended content, writing evidence,
and model provider. It will then create a separate workspace pinned to an
immutable Core release.

Prefer doing it yourself? Follow
[Create a thin content workspace](docs/guides/creating-a-content-workspace.md)
for the complete terminal instructions and configuration options.

## How it works

The author first establishes an approved voice, then uses it in a repeatable
content loop. Core's rules remain authoritative underneath every agent.

### Voice setup

```mermaid
flowchart TD
    A["Create or open an author workspace"] --> B["Inspect persisted state<br/>with Start or Overview"]
    B --> C{"Choose a voice route"}
    C -->|"Authorised writing"| D["Measure a linguistic signature<br/>and build a voice candidate"]
    D --> E["Voice Analyst"]
    E --> F["Profile Critic"]
    F --> G["Voice Evaluator"]
    C -->|"No writing yet"| H["Use the neutral<br/>Clear Professional Starter"]
    G --> I{"Human review"}
    H --> I
    I -->|"Approve"| J["Activate an immutable voice version"]
    I -->|"Revise"| C
```

### Content loop

```mermaid
flowchart TD
    A["Describe the content in ordinary language"] --> B["Coordinator resolves voice, pack,<br/>provider, perspective, and research route"]
    B --> C["Briefing Agent"]
    C --> D{"Research required?"}
    D -->|"Yes"| E["Researcher and research approval"]
    D -->|"No"| F["Writer"]
    E --> F
    F --> G["Critic and deterministic validators"]
    G --> H["Attribution Reviewer when required"]
    H --> I{"Human editorial review"}
    I -->|"Revise"| B
    I -->|"Approve"| J["Save inside the author repository"]
    J --> K["Learning Extractor updates<br/>only the active voice's learning"]
    K -. "future request" .-> B
```

Throughout both flows, persisted files—not chat history—hold workflow state.
Core does not silently change a voice or perspective, invent identity or
evidence, add research to a no-research route, or publish externally.

### 1. Create an author workspace

The generated repository belongs to the author. It keeps their editorial
material separate from the reusable engine and can have its own writer,
researcher, critic, policies, and learning.

Core is installed as a versioned dependency; its source code is not copied
into each content repository.

### 2. Choose a voice route

The author chooses one of two starting points:

- **Use previous writing** to build a reviewable voice candidate from
  authorised documents or URLs.
- **Start without previous writing** using the neutral Clear Professional
  Starter, which does not claim to imitate the author.

No candidate becomes active without human approval. A new subject also does
not automatically require a new voice; it may be better represented as a
separately governed perspective.

See [Voice onboarding](docs/guides/voice-onboarding.md) for the commands and
lifecycle, or [How voice is derived](docs/guides/how-voice-is-derived.md) for
the underlying analysis and safeguards.

#### Statistical voice evidence

For a source-derived voice, Core calculates a deterministic linguistic
signature from the authorised corpus. It records per-source measurements and
descriptive statistics for rhythm, structure, stance, punctuation, and lexical
diversity, separated by register where possible. These measurements are
evidence for human review: they are not generation targets, personality
inferences, forensic authorship attribution, or proof that a feature is unique
to the author.

Read the [statistical and linguistic voice
framework](docs/guides/linguistic-voice-framework.md), or inspect a built
candidate with `content-creator voice signature <voice-id>`.

Core can also calculate an optional `statistical_voice_score` for a draft using
either deterministic distribution comparison or an explicitly trained ML
classifier. Scoring is disabled by default and remains critic-only advisory
evidence: it is not an authorship probability, writing target, quality-gate
input, or publication gate. Automatic workflow scoring additionally requires
an eligible long-form content pack. The explicit `voice score` command remains
available for deliberate, ad hoc assessment of any sufficiently long text.

### 3. Ask for content naturally

Open the author workspace in a supported coding assistant and describe what
you need:

> Write a short LinkedIn post explaining why calculus matters to sixth-form
> students. No external research is required.

The Content Creator Coordinator reads the workspace state, proposes the
appropriate voice and format, follows the required research and review
checkpoints, and preserves the run artifacts.

Automation and agent hosts can attach an `--idempotency-key` to a run. An
equivalent retry returns the existing `run_id` and state instead of executing
the content route twice; conflicting reuse fails safely. Intentional revisions
use a new key plus `--parent-run`.

The result always comes back for human review. “Publish” means saving an
approved copy inside the author repository; Core does not post to external
platforms.

Content packs can also opt into provider-independent visual assets. Core owns
typed briefs, renderer/provider adapters, asset lineage, deterministic
validation, critique, approval, and publication gating; packs own platform
dimensions and crop behaviour, while author workspaces retain visual voice.
See [Visual asset workflows](docs/guides/visual-assets.md).

Recovered Core diagnostics remain out of the editorial conversation until the
author approves the piece. At that publication boundary, Core presents one
sanitised, consolidated support candidate and keeps external issue submission
under explicit human control. Fatal Core diagnostics are surfaced immediately.

See [Content Creator Coordinator](docs/guides/content-coordinator.md) for
conversational and direct terminal use.

## What the author controls

The author workspace owns:

- voice evidence, candidates, approvals, and immutable versions;
- perspectives and their provenance;
- repository-specific agents and editorial policies;
- repository-wide and voice-scoped learning;
- research, drafts, critiques, and run history; and
- approved content.

Core owns the reusable orchestration, schemas, provider adapters, validation,
checkpoints, safety rules, prompt composition, and workspace generator.

## Important boundaries

- The author remains the final editorial authority.
- Core does not invent personal experience, beliefs, facts, or voice evidence.
- Voices and learning are isolated from one another.
- No-research requests remain no-research.
- Voice activation and repository publication require explicit approval.
- External publication is not supported.

## Guides

Use the [task-oriented documentation index](docs/README.md) to create a
workspace, manage a voice, create content, maintain a downstream repository, or
develop Core. Detailed terminal procedures remain in the focused guides.

## Work on Content Creator Core

Clone this repository only when you want to inspect or change the reusable
engine. The [Core development guide](docs/core/README.md) covers installation,
architecture, testing, and releases. The
[engineering standards](docs/core/engineering-standards.md) define the required
quality, compatibility, security, and release controls.

External code contributions are not currently accepted. Bug reports and
feature requests are welcome through GitHub Issues; read
[Contributing](CONTRIBUTING.md) first. Report security-sensitive issues through
the private process in the [security policy](SECURITY.md).

## Licence

Content Creator is free and open-source software licensed under the
[GNU Affero General Public License, version 3 or later](LICENSE.md)
(`AGPL-3.0-or-later`). Commercial use is permitted subject to the licence
terms. See [Licensing](LICENSING.md) for a plain-language overview.

Copyright © 2026 Bharath Vadhoola
