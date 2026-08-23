# Understand agents, learning, voice, and perspectives

An author workspace keeps personal material separate from the reusable Core.
Use one read-only command to see how those layers currently combine:

```bash
content-creator --workspace . personalisation show
```

Use `--json` when a chat host or another tool needs the same structured view.

To see the exact sources a particular role would receive, use the read-only
preflight:

```bash
content-creator --workspace . personalisation explain \
  --role writer --voice bharath-linkedin --pack linkedin-post
```

See [runtime context composition](runtime-context-composition.md) for live and
historical traces.

## Who are my agents and how are they personalised?

The report lists every role, its purpose, and its editable file under `agents/`.
It labels that file as `customised`, `core-starting-point`, or `missing`. Core's
mandatory harness and role contract still apply around that editable
specialisation.

The agent file is deliberately stable. Author feedback does not silently
rewrite it. Instead, active learning is composed into the effective prompt at
runtime so its evidence and lifecycle remain inspectable.

## What have my agents learnt?

Repository-wide learning lives in `learnings/memory.json`. Learning associated
with a selected voice lives in
`profiles/<voice-id>/learnings/<voice-version>/memory.json`. The report shows the actual
principles and their role and status, not only a count.

Visual preferences live separately in
`profiles/<voice-id>/visual-learnings/memory.json`. They are shown as scope
`visual` and enter visual briefs only; they never enter writer, critic, or
linguistic voice prompts. Record explicit visual direction with:

```bash
content-creator --workspace . visual learn <run-id> \
  --feedback "Prefer one dominant metaphor with restrained colour and negative space."
```

Only active, role-matched learning enters a prompt. For example, an active
writer principle under `profiles/bharath-linkedin/learnings/1.0.0/memory.json` is
supplied to the writer whenever `bharath-linkedin` is selected. A provisional
critic principle remains visible for review but is not supplied to the writer
or critic until activated.

## Where are my perspectives and voice?

Each voice is under `profiles/<voice-id>/`. The report identifies its active
immutable version, voice-specific learning, approved perspectives, pending
perspective candidates, rejected voice candidates, and any voice candidate
still requiring a decision.

A voice governs expression. A perspective represents an approved position or
interpretation. Core keeps them separate so learning a writing habit does not
silently invent a belief. Visual preference is a third explicit scope so image
direction does not silently change linguistic expression.

The report also shows whether an active voice has locally discoverable new
evidence or unconsolidated active learning. This is advisory eligibility, not
an automatic upgrade. Use the reported `voice upgrade-plan` command to create
a hash-bound inventory and review every learning disposition.

## Effective prompt order

Core composes the applicable layers in this order:

1. mandatory Core harness;
2. mandatory Core role contract;
3. repository-owned agent specialisation;
4. repository learning policy;
5. selected active voice;
6. approved perspectives;
7. active repository-wide and voice-specific learning; and
8. rubrics and content-pack instructions.

Some layers apply only to the roles that consume them. The JSON report includes
the exact role mapping.

Each real model invocation also writes exact loaded and skipped source evidence
to `runs/<run-id>/context-composition.json`. This includes selected learning
record IDs, so a writer run can prove which `bharath-linkedin` principles it
received without duplicating their private text.

## Candidate decisions

`personalisation show` and `voice status` distinguish a genuinely pending
candidate from a candidate copy whose hash is already active. To reject an
unwanted candidate without changing the active voice, use the exact hash shown
in the report:

```bash
content-creator --workspace . voice reject <voice-id> \
  --candidate-hash sha256:<complete-hash> \
  --rejected-by "<author>" \
  --reason "<reason>"
```

Core archives an immutable rejection snapshot and receipt, removes the pending
candidate, and leaves the active registry entry and version unchanged.

## Lifecycle state and valid actions

The report distinguishes `active`, `inactive`, and `retired`, shows the recorded
actor, reason, and time, and offers only valid next actions. Inactive voices can be
reactivated without a content-version change. Retired voices expose a restore plan,
historical inspection, and offline verification—not ordinary reactivation. A default
voice that is withdrawn must be explicitly cleared or replaced with a verified active
voice. See [Voice retirement](voice-retirement.md).
