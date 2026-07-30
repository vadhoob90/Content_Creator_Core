# Content Creator Coordinator

The Content Creator Coordinator is a conversational interface over Core. It is
not a replacement for Core's deterministic orchestrator.

## Responsibility boundary

The coordinator may interpret a request, inspect workspace state, propose a
work order, invoke typed Core commands, explain artifacts, and present the next
valid actions. Core remains authoritative for routing, persisted state,
validation, voice activation, research approval, and repository publication.

Chat history is never workflow state. Agent hosts should begin with:

```bash
content-creator --workspace . coordinator context
```

Authors can use the calmer human-readable entry points:

```bash
content-creator --workspace . overview
content-creator --workspace . start
content-creator --workspace . start "Write a concise launch announcement"
```

`overview` renders active voice and version, provider state, default pack,
incomplete runs, warnings, and one recommended action. `overview --json`
returns the same typed snapshot used by agent hosts.

`start` is read-only. With no request it routes the author to setup, onboarding,
an interrupted run, or draft review. With a request it proposes the voice,
format, pack, research route, perspective handling, and approval points. The
author must still invoke any mutating or approval command explicitly.

## JSON compatibility

The v0.5 `coordinator context` fields remain available with their existing
meanings, including the string-valued `provider`. The v0.6 snapshot adds
`provider_status`, `health`, `recommended_action`, and per-run `incomplete`
metadata. Hosts should ignore unknown fields. Mutating action arrays retain
their existing commands and confirmation flags.

For an existing run:

```bash
content-creator --workspace . coordinator next-actions <run-id>
```

The returned commands are argument arrays so a host does not need to parse a
shell command. Mutating actions identify whether explicit human confirmation is
required.

## Workspace policy

Each downstream repository may configure the interface:

```yaml
coordinator:
  name: Alice Content Coordinator
  default_voice: alice-general
  default_pack: linkedin-post
  ask_before_voice_change: true
  require_final_review: true
  external_publication: disabled
  review_reminder: Review all factual and personal claims before approval.
```

Defaults reduce repetitive questions but do not override an explicit request.
External publication is intentionally unsupported. `publish` means an approved
copy inside the repository.

## Voice versus perspective

The coordinator must not equate a new subject with a new voice. It should
propose:

- a new voice when register, audience, channel, or evidence corpus is
  meaningfully different; or
- a perspective context when the same voice needs separately governed
  subject-matter positions.

The author chooses. Voice and perspective creation remain explicit,
deterministic lifecycle operations.

## Host integration

Core packages Codex-compatible `content-creator` and `voice-builder` skills into
new workspaces. Other hosts can use the same coordinator JSON interface without
copying routing or approval logic into a prompt.

## Direct terminal use

Most authors can work conversationally. The same deterministic interface is
available from the terminal when inspecting or automating a workspace:

```bash
uv run content-creator --workspace . coordinator context
uv run content-creator --workspace . coordinator runs
uv run content-creator --workspace . coordinator next-actions <run-id>
```

Create a run directly:

```bash
uv run content-creator --workspace . run \
  "Explain why calculus matters to sixth-form students" \
  --voice alice-general \
  --pack linkedin-post \
  --research none
```

After the author reviews the resolved draft, save an approved copy inside the
repository:

```bash
uv run content-creator --workspace . publish <run-id> \
  --feedback "Preserve the concrete opening."
```

Repository publication never overwrites an existing file, updates only the
selected voice's learning memory, and does not post to an external platform.
