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
