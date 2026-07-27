# Content Creator: Claude Code instructions

The workflow contracts are provider-neutral. Claude Code is one entry point and
must follow the same definitions as every other runtime.

## Load the selected contracts

- `agents/README.md`
- `agents/briefing-agent.md` when the request is materially ambiguous
- `agents/researcher.md` and its learnings contract for research routes
- `agents/writer.md`, the active profile, and the selected pack for drafting
- `agents/critic.md`, the active profile, core rubric, pack rubric, and research
  overlay for review
- `agents/learning-extractor.md` after repository publication

Resolve profiles from `profiles/<voice-id>/`; never use one voice's profile or
learnings for another.

## Workflow boundaries

- The Briefing Agent structures intent; it does not select models or run stages
- The researcher produces evidence; it does not write prose
- The writer drafts and revises; it does not research or approve itself
- Deterministic validators own mechanical rules
- The critic provides structured assessment; it does not control the loop
- The orchestrator owns routes, checkpoints, persistence, and iteration
- The author owns scope, personal truth, and final approval

The LinkedIn packs support post/article crossed with none/light/deep research.
Deep agent research requires author approval of the research brief.

## Publication and learning

An instruction to move the reviewed piece into its pack's published directory
is author approval. Resolve the exact run, never overwrite, surface factual
blockers, call `content-creator publish`, and report learning changes.
Repository publication never means external distribution.

Explicit feedback may become active learning. Publication-only inference
remains provisional. Never rewrite a stable voice profile from one session.
