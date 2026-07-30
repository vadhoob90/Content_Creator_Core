---
name: content-creator
description: Plan, research, draft, review, publish, and learn from content using the repository's provider-neutral workflow, including optional context-isolated author perspectives. Use for LinkedIn posts or articles, generic content runs, research checkpoints, revisions, run status, perspective creation or approval, repository publication, publication-triggered voice learning, and perspective proposals.
---

# Content Creator

Work from the repository root and preserve every run artifact.

## Begin with Core state

Before choosing commands or asking the author to remember identifiers, run:

```bash
content-creator --workspace . start
```

Use the recommended action derived from Core's typed workspace state. For a
machine-readable snapshot, run `coordinator context`; for a human-readable
summary, run `overview`. A configured default voice is a proposal, not
permission to ignore an explicit voice choice. Never reconstruct lifecycle
state from chat memory.

For an existing run, ask Core what can happen next:

```bash
content-creator --workspace . coordinator next-actions <run-id>
```

Only offer actions returned for the persisted state. Commands marked as
requiring confirmation need explicit author approval.

## Start a request

1. Run `content-creator start "<request>"` when format or research depth is not
   explicit.
2. Show the resolved work order if the briefing decision is material or asks
   for clarification.
3. Run with explicit flags when the request is clear:

```bash
content-creator run "<request>" \
  --pack general-text \
  --voice <active-voice-id> \
  --research none \
  --provider codex-native
```

Execution choice changes only
`--provider anthropic|openai|codex-native|claude-native`. Do not rewrite the
author's request for a provider. Native modes require a subscription login and
must never fall back to API-key billing. When working interactively in Codex
and the author has not selected a provider, prefer `codex-native`.

Resolve only active voices. Preserve the exact pack and voice version written
to `runs/<run-id>/resolved-context.json`. Use `$voice-builder` when the user
asks to create, approve, deactivate, or otherwise manage a voice.

## Manage optional perspectives

Treat perspective as an approved author position, never factual authority or
part of linguistic voice. Do not infer a context from topic similarity.

Create and approve a named context only from explicit author evidence:

```bash
content-creator perspective create \
  --voice <voice-id> \
  --context <context-id> \
  --statement "<author-supplied position>" \
  --evidence "<direct evidence>"

content-creator perspective verify \
  --voice <voice-id> --context <context-id>

content-creator perspective approve \
  --voice <voice-id> \
  --context <context-id> \
  --approved-by "<approver>"
```

Use `--perspective-context <context-id>` only when explicitly requested. Keep
contexts isolated. Publication may create proposals; inspect with `perspective
proposals`, stage one with `perspective stage-proposal`, then require another
explicit deterministic approval. Never claim a proposal is active.

## Follow the route

- Never add research to a `none` route.
- Use `light` for bounded verification and `deep` for broad synthesis,
  historical analysis, or contested claims.
- If a run reaches `awaiting_research_approval`, show `research.json` and wait
  for the author. Resume only with `content-creator approve-research <run-id>`.
- Show `final.md` when the run is `ready` or `needs_author`.
- Preserve work orders, route plans, claim provenance, research, drafts,
  perspective evaluation, validation, critiques, quality decisions, and model
  selections under `runs/<run-id>/`.

## Finalise

Treat an instruction to move the active piece into its published directory as
author approval:

```bash
content-creator publish <run-id> --feedback "<explicit feedback, if any>"
```

Publication writes only to the selected pack's repository destination. It does
not post externally. It then records approval and updates only the active
voice's learning memory. Explicit feedback may become active learning;
publication-only inference remains provisional.

When a run resolves a perspective context, publication may create proposals
only in that context. Perspective proposals never become active without a
separate author approval command.

Do not commit or push unless the user explicitly asks.
