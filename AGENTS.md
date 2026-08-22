# Content Creator repository guidance

This repository contains a provider-neutral content workflow with
channel-specific content packs and voice-scoped profiles.

## Content requests

Treat natural requests to create or revise supported content as an invocation
of the `content-creator` workflow.

1. Create or validate a work order
2. Resolve content pack, voice, research depth, and research source
3. Ask only questions that materially change scope or route
4. Follow the core contracts and repository-owned agents
5. Load repository learnings plus only the selected voice's learnings
6. Apply the core rubric, selected pack rubric, and research overlay
7. Preserve research, drafts, critiques, validation, and route artifacts
8. Return the final draft for author review

Attach one stable `--idempotency-key` when an exact run invocation may be
retried. Reuse it only for the equivalent submission; changed requests and
intentional revisions require a new key. Revisions also use `--parent-run`.

## Approval trigger

When the user instructs you to move the active draft into the selected pack's
published directory, treat that as approval. Never overwrite an existing
publication and never publish externally.

If Core returns `awaiting_diagnostic_decision`, surface the consolidated,
sanitised support candidate once at this publication boundary. Ask whether to
publish only or publish and prepare a Core issue. Do not surface recovered
diagnostics during normal draft iterations. Surface fatal Core diagnostics
immediately.

After the move, run learning extraction and update only the active voice's
incremental learning memory.

## Boundaries

- The author is the final editorial authority
- The critic does not control orchestration
- A score does not override a factual-integrity blocker
- Do not perform research in no-research routes
- Do not invent sources, facts, personal context, or voice evidence
- Do not mix profiles or learnings between voices
- Do not commit or push unless explicitly requested

## Core module map

- `orchestrator.py` coordinates lifecycle checkpoints through a composed runtime.
- `stages.py` and `capabilities.py` define replaceable execution seams.
- `commands/` owns CLI parsing and dispatch; domain behavior stays outside it.
- Command handlers invoke application boundaries and render results. They do not
  construct mutable run stores, call private persistence methods, reach through
  `orchestrator.store`, or move terminal output into inner services.
- `providers/` contains the provider contract, registry, fakes, and adapters.
- `diagnostics/` owns privacy-safe runtime evidence and support candidates.
- `voice_build/` owns voice-build models, rendering, and pipeline execution.
- `voice_ml/` owns optional training dependencies, training, and inference.
- `workspace.py`, `workspace_scaffolding.py`, and `workspace_templates.py` generate
  thin author repositories without overwriting author-owned files.

Start structural work in `docs/core/architecture-guardrails.md`. Start provider,
stage, or pack extensions in `docs/guides/extending-core.md`.
Preserve inward dependencies and run `python scripts/architecture_report.py --check`;
CI blocks reverse edges even when they do not form an import cycle.

## Verification

Use `content-creator doctor` for offline configuration checks,
`content-creator eval` for the replay route matrix, and `pytest` for the
software suite. Live provider evaluation is explicit and consumes either API
spend or native subscription allowance.
