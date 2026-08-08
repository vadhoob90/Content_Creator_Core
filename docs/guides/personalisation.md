# Understand agents, learning, voice, and perspectives

An author workspace keeps personal material separate from the reusable Core.
Use one read-only command to see how those layers currently combine:

```bash
content-creator --workspace . personalisation show
```

Use `--json` when a chat host or another tool needs the same structured view.

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
`profiles/<voice-id>/learnings/memory.json`. The report shows the actual
principles and their role and status, not only a count.

Only active, role-matched learning enters a prompt. For example, an active
writer principle under `profiles/bharath-linkedin/learnings/memory.json` is
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
silently invent a belief.

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
