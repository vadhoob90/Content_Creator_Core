# Understand runtime context composition

Every model invocation receives two kinds of context: ordered system
instructions and task-specific input. Content Creator records where both came
from without storing another copy of private prompt content.

## What is injected, and in what order?

For each role, Core composes the applicable instruction layers in this order:

1. `contracts/agent-harness.md` from the installed Core package;
2. `contracts/roles/<role>.md` from Core;
3. `agents/<role>.md` from the author workspace;
4. `agents/<role>-learnings.md` from the workspace, where the role has a
   learning policy;
5. the selected immutable voice profile under `profiles/<voice-id>/`;
6. only the approved perspective profiles selected for this run;
7. active, role-matched records from `learnings/memory.json` and the exact
   `profiles/<voice-id>/learnings/<resolved-voice-version>/memory.json` epoch; and
8. the selected content pack's rubrics and role instructions.

A layer that does not apply is recorded as `skipped` with a reason. This makes
absence visible—for example, `no-approved-perspective-selected` or
`no-active-role-matched-learning`.

Voice learning resolution is pinned to the run's immutable voice version. A
version 1 run cannot read or mutate version 2 memory. When an upgrade
incorporates a version 1 learning into version 2 guidance, the record remains in
the frozen version 1 epoch and is absent from the fresh version 2 runtime epoch,
preventing duplicate injection without prompt-time heuristics.

The task instruction and structured payload are then sent as user context.
Their contents can include the work order, research, a draft, prior criticism,
or explicit feedback depending on the lifecycle phase. The composition record
stores hashes, top-level keys, and run-artifact locators for these inputs, not
their contents.

## Preview the expected context

Use the read-only preflight before creating content:

```bash
content-creator --workspace . personalisation explain \
  --role writer \
  --voice bharath-linkedin \
  --pack linkedin-post \
  --research none
```

Add `--perspective-context <id>` once for each explicitly selected perspective.
Use `--json` for the same ordered report as structured data. Preflight resolves
current workspace state but does not create a run or invoke a provider.

## Watch composition while content is created

Add `--show-context` to a normal run:

```bash
content-creator --workspace . run "Write a useful LinkedIn post" \
  --pack linkedin-post \
  --voice bharath-linkedin \
  --research none \
  --show-context
```

Core writes concise lines such as these to standard error before each provider
invocation:

```text
[context]   1. load Core harness from core:contracts/agent-harness.md
[context]   3. load Workspace writer agent from agents/writer.md
[context]   7. load Active voice learnings from profiles/bharath-linkedin/learnings/memory.json; records=writer-01
```

Standard output remains the normal machine-readable run result, so existing
automation is unaffected.

## Inspect a historical run

Every new run with an agent invocation stores
`runs/<run-id>/context-composition.json`. Inspect it with:

```bash
content-creator --workspace . context show <run-id>
content-creator --workspace . context show <run-id> --json
```

The manifest records invocation order, lifecycle phase, provider and model,
loaded and skipped sources, source hashes and versions, and selected learning
or perspective record IDs. Runs created before Core v1.6.0 do not have this
artifact.

## Privacy boundary

The manifest deliberately does not duplicate system prompts, drafts, feedback,
research text, credentials, or unselected private voice and perspective
material. A hash proves which private task input was used without making the
manifest another store of that content. The original authorised files and run
artifacts remain the source of truth.
