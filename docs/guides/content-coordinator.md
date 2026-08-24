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
content-creator --workspace . setup
content-creator --workspace . overview
content-creator --workspace . start
content-creator --workspace . start "Write a concise launch announcement"
content-creator --workspace . personalisation show
```

`setup` derives four milestones from the same typed coordinator state:
workspace readiness, writing-style choice, model connection, and the first
piece. It supplies exact actions using identifiers Core already knows. The
neutral-starter path can reach content creation immediately; source-derived
personalisation remains a separate evidence and review process. Provider
selection is persisted only after verification, and usage-billed providers
require explicit confirmation.

`overview` renders active voice and version, provider state, default pack,
incomplete runs, warnings, and one recommended action. `overview --json`
returns the same typed snapshot used by agent hosts.

`personalisation show` answers who the agents are, which editable definitions
have been customised, what active principles they have learnt, and where the
selected voice and approved perspectives live. See the
[personalisation guide](personalisation.md).

`start` is read-only. With no request it routes the author to setup, onboarding,
an interrupted run, or draft review. With a request it proposes the voice,
format, pack, research route, perspective handling, and approval points. The
author must still invoke any mutating or approval command explicitly. With a
request, it may show the proposed plan before setup is complete, but it does
not offer `run` until an active writing style and verified provider are ready.

## JSON compatibility

The v0.5 `coordinator context` fields remain available with their existing
meanings, including the string-valued `provider`. The v0.6 snapshot adds
`provider_status`, `health`, `recommended_action`, and per-run `incomplete`
metadata. Hosts should ignore unknown fields. Mutating action arrays retain
their existing commands and confirmation flags.

Core 1.15 adds `content_session_id`, `parent_run_id`, `authoritative`, and
`superseded_by_run_id` to each run summary. Coordinator recommendations operate
on the latest authoritative descendant in a revision lineage, so a published
child does not leave an older ready parent as the apparent active draft. A
published run with `pending_learning_count` exposes a confirmed
`retry-learning` action without reopening publication.

For an existing run:

```bash
content-creator --workspace . coordinator next-actions <run-id>
```

The returned commands are argument arrays so a host does not need to parse a
shell command. Mutating actions identify whether explicit human confirmation is
required.

Hosts that may retry a `run` invocation should generate one stable
`--idempotency-key` for that exact submission. If completion is unclear, retry
with the same key or call `submission status <key>`; Core returns the existing
run instead of executing it again. A changed request or intentional revision
must use a new key. Revisions should also pass `--parent-run <run-id>`.

Recovered Core diagnostics are not presented during ordinary drafting. When
the author approves publication, `publish` either completes normally or
returns `awaiting_diagnostic_decision` without moving the draft. The host must
then present the consolidated candidate once and offer the returned
`publish-only` and `publish-and-prepare-issue` actions. Fatal Core diagnostics
are exposed immediately because there may be no later publication boundary.

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

If Core pauses for diagnostics, repeat the approved publication with the
author's separate diagnostic choice:

```bash
uv run content-creator --workspace . publish <run-id> \
  --diagnostic-decision publish-only

uv run content-creator --workspace . publish <run-id> \
  --diagnostic-decision prepare-issue
```

Repository publication never overwrites an existing file, updates only the
selected voice's learning memory, and does not post to an external platform.

## Defaults, withdrawal, and unfinished runs

The coordinator never silently redirects an inactive or retired default voice.
`voice retirement-plan` inventories the default decision, pending candidates and
proposals, owned perspective contexts, learning epoch, and every incomplete or
publishable run. The author explicitly clears or replaces a withdrawn default and
chooses whether named unfinished runs are completed, abandoned with an auditable
decision, or retained behind an exact exception. Retirement blocks new revisions,
publication, learning, upgrades, and candidate activation; historical inspection and
verification remain available. Coordinator and personalisation views show the reason,
decision time, unresolved dispositions, and only valid next actions.
