# Content Creator repository guidance

This repository contains a provider-neutral content workflow with
channel-specific content packs and voice-scoped profiles.

## Content requests

Treat natural requests to create or revise supported content as an invocation
of the `content-creator` workflow.

1. Create or validate a work order
2. Resolve content pack, voice, research depth, and research source
3. Ask only questions that materially change scope or route
4. Follow the role contracts under `agents/`
5. Load the selected voice profile and only its learnings
6. Apply the core rubric, selected pack rubric, and research overlay
7. Preserve research, drafts, critiques, validation, and route artifacts
8. Return the final draft for author review

## Approval trigger

When the user instructs you to move the active draft into the selected pack's
published directory, treat that as approval. Never overwrite an existing
publication and never publish externally.

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

## Verification

Use `content-creator doctor` for offline configuration checks,
`content-creator eval` for the replay route matrix, and `pytest` for the
software suite. Live provider evaluation is explicit and paid.
