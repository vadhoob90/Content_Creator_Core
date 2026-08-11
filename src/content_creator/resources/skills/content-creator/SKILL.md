---
name: content-creator
description: Plan, research, draft, review, create governed images, publish, and learn from content using the repository's provider-neutral workflow, including optional context-isolated author perspectives. Use for LinkedIn posts or articles, image requests for active content, generic content runs, research checkpoints, revisions, run status, perspective creation or approval, repository publication, publication-triggered voice learning, and perspective proposals.
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

When the author asks who their agents are, what the agents have learnt, or
where voice and perspectives live, run the read-only inspection:

```bash
content-creator --workspace . personalisation show
```

Before a run, use `personalisation explain --role <role>` to preview the exact
Core, workspace, voice, perspective, learning, and pack sources that would be
composed. For live evidence, add `--show-context` to `run`; the trace is written
to stderr and does not change the normal result on stdout. For a persisted run,
use:

```bash
content-creator --workspace . context show <run-id>
```

Treat `runs/<run-id>/context-composition.json` as the privacy-safe provenance
record. It contains source hashes, versions, selected record IDs, and private
task-input hashes, not duplicated prompt or draft contents.

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
`--provider anthropic|bedrock|openai|codex-native|claude-native`. Do not rewrite the
author's request for a provider. Native modes require a subscription login and
must never fall back to API-key billing. When working interactively in Codex
and the author has not selected a provider, prefer `codex-native`.

Resolve only active voices. Preserve the exact pack and voice version written
to `runs/<run-id>/resolved-context.json`. Use `$voice-builder` when the user
asks to create, approve, deactivate, or otherwise manage a voice.

## Create a visual for reviewed content

Treat “create an image for this post/article” as an invocation of Core's visual
workflow, not as permission to use an untracked host image tool. Run `start` to
resolve workspace state, then use `coordinator next-actions <run-id>` when an
active run is known. If more than one reviewed run could be meant, ask the
author which run; do not guess. Preserve the author's exact request:

```bash
content-creator --workspace . visual components <run-id> [--role <role>]
content-creator --workspace . visual render <run-id> \
  --request "<exact author request>" [--role <role>] [--variants 2]
```

Core resolves reusable components from the installed pinned package, combines
pack-owned role requirements with optional workspace-owned
`visual-brand.json` tokens, renders named variants, validates them, and records
the routing decision and component versions under `runs/<run-id>/visuals/`.
Present variants for critique, selection, and explicit approval. Never bypass
the visual lifecycle when a pack, role, component, or adapter is unavailable;
surface Core's diagnostic and offer only supported roles returned by
`visual components`.

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
- When revising an existing piece through another run, pass
  `--parent-run <run-id>`. Core carries the parent's `content_session_id`
  forward so recovered diagnostics are consolidated across the complete
  editorial lineage.
- When an exact run invocation may be retried, attach one stable
  `--idempotency-key` and reuse it only for that equivalent submission. If the
  outcome is unclear, retry with the same key or inspect it with `submission
  status <key>`. Never reuse the key for changed instructions. A deliberate
  revision uses a new key together with `--parent-run`.

## Finalise

Treat an instruction to move the active piece into its published directory as
author approval:

```bash
content-creator publish <run-id> --feedback "<explicit feedback, if any>"
```

If publication returns `awaiting_diagnostic_decision`, do not treat it as a
failure and do not silently choose for the author. Present the sanitised,
consolidated Core support candidate once and offer the exact returned actions:
publish only, publish and prepare an issue, or inspect the diagnostic. Do not
surface recovered diagnostics during ordinary draft iterations. Fatal Core
diagnostics are surfaced immediately because there may be no publication
boundary. After `prepare-issue`, use the host's authenticated GitHub
integration to search for duplicates and obtain explicit approval before
creating or updating an issue. Then record the resulting URL with
`diagnostics link-issue`.

Publication writes only to the selected pack's repository destination. It does
not post externally. It then records approval and updates only the active
voice's learning memory. Explicit feedback may become active learning;
publication-only inference remains provisional.

Successful publication also writes a tracked, privacy-safe receipt under
`publication-receipts/`. Before committing a publication, run:

```bash
content-creator verify-publications
```

This verification is deterministic and offline. Surface enforced hash,
provenance, voice, perspective, or missing-receipt failures before committing.
Do not replace a legacy baseline unless the author explicitly approves the
reviewed legacy set.

If publication returns `review_required`, present the finding codes and the
ignored assessment artifact. The author may revise the draft, or explicitly
approve the unchanged review with:

```bash
content-creator publish <run-id> \
  --perspective-review-approved-by "<reviewer>" \
  --perspective-review-notes "<optional decision context>"
```

Never choose this approval on the author's behalf. Model-assisted findings may
pause for review but cannot reject, approve, or redefine the author's position.

If the author supplies durable feedback after publication, or for a reviewed
run that should not be published yet, use the learning-only operation:

```bash
content-creator learn <run-id> --feedback "<explicit author feedback>" \
  --idempotency-key <stable-retry-key>
```

This operation must not create, replace, or duplicate a publication. Reuse the
same key only for the same run and feedback; intentional new feedback uses a
new key.

When a run resolves a perspective context, publication may create proposals
only in that context. Perspective proposals never become active without a
separate author approval command.

Do not commit or push unless the user explicitly asks.
