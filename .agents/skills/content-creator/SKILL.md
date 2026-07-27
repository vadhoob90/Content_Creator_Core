---
name: content-creator
description: Plan, research, draft, review, publish, and learn from content using the repository's provider-neutral workflow. Use for LinkedIn posts or articles, generic content runs, research checkpoints, revisions, run status, repository publication, and publication-triggered voice learning.
---

# Content Creator

Work from the repository root and preserve every run artifact.

## Start a request

1. Run `content-creator plan "<request>"` when format or research depth is not
   explicit.
2. Show the resolved work order if the briefing decision is material or asks
   for clarification.
3. Run with explicit flags when the request is clear:

```bash
content-creator run "<request>" \
  --pack linkedin-post \
  --voice default \
  --research none \
  --provider anthropic
```

Provider choice changes only `--provider anthropic|openai`. Do not rewrite the
author's request for a provider.

## Follow the route

- Never add research to a `none` route.
- Use `light` for bounded verification and `deep` for broad synthesis,
  historical analysis, or contested claims.
- If a run reaches `awaiting_research_approval`, show `research.json` and wait
  for the author. Resume only with `content-creator approve-research <run-id>`.
- Show `final.md` when the run is `ready` or `needs_author`.
- Preserve work orders, route plans, research, drafts, validation, critiques,
  quality decisions, and model selections under `runs/<run-id>/`.

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

Do not commit or push unless the user explicitly asks.
