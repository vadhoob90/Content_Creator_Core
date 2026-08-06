# Routes and work orders

`WorkOrder` is the provider-neutral hand-off from briefing to orchestration.
Its routing fields are `content_pack`, `format`, `research_depth`, and
`research_source`; `voice_id` selects the isolated profile and learning
namespace.

| Format | Depth | Source | Checkpoint |
|---|---|---|---|
| post | none | none | no |
| post | light | agent or supplied | no |
| post | deep | agent | after research |
| article | none | none | no |
| article | light | agent or supplied | no |
| article | deep | agent | after research |

Deep supplied research skips the researcher checkpoint because the author
supplied the evidence. The critic and evidence rules still apply.

Explicit author instructions win. Deterministic briefing handles phrases such as
“no research” or “deep research” without spending a model call. Materially
ambiguous requests go to the Briefing Agent, which may return focused
clarification questions rather than guessing.

Deep agent research persists `research.json` and returns
`awaiting_research_approval`. `approve-research` resumes from disk;
`reject-research` records the author's decision and stops before drafting.

Supplied research is a preflight input. Core reads its JSON, validates the
`ResearchBrief` schema, and verifies that every evidence URL exists in the
brief's source list before allocating a normal run. Missing, malformed, or
referentially invalid supplied briefs are recorded as invocation diagnostics
under `.content-creator/invocations/`; they do not create failed entries under
`runs/`. Agent-generated research remains part of the persisted run because it
is produced during execution.

`--research-file` accepts UTF-8 JSON only. The object must contain `summary`,
`evidence`, `sources`, `tensions`, and `gaps`; Markdown input is rejected with
an example of the supported contract before a run is persisted.

Research-backed output uses `--citation-style inline-links` by default. Use
`--citation-style numbered-references` when the draft must include numbered
in-text markers and a `References` section containing source URLs.

## Idempotent submission and intentional revisions

Callers that may retry an uncertain invocation should supply a stable key:

```bash
content-creator --workspace . run \
  "Write the launch post" \
  --pack linkedin-post \
  --voice <voice-id> \
  --idempotency-key launch-post-request-1
```

Core hashes the key before persistence and atomically associates it with a
canonical fingerprint and one `run_id`. Repeating the equivalent submission
returns that run at its current state without rerunning research, drafting,
review, learning, or publication. Reusing the key with a different work order
fails as a workflow validation error.

Inspect a known submission without executing it:

```bash
content-creator --workspace . submission status launch-post-request-1
```

The command works while the run is active and after it reaches a terminal or
human-checkpoint state. Normal `status <run-id>` and `coordinator next-actions
<run-id>` remain authoritative for continuation. Research approval and
publication retain their existing state gates and are never repeated by
idempotent submission.

A new editorial direction can still use `--parent-run <prior-run-id>` to create
a distinct run. To change a reviewed draft while retaining its existing run,
use `content-creator revise RUN_ID --feedback "..."`. Pass `--draft-file` when
the author has already edited the Markdown. Core preserves the baseline and a
unified diff, records feedback as run-scoped, and reruns validation, voice and
perspective evaluation, criticism, quality scoring, and provenance updates.

Attach `--idempotency-key` when retrying an exact revision. A completed retry
returns the existing revision; an interrupted retry resumes the recorded
request. Reusing the key with different feedback or draft content is rejected.

Older runs that copied a pack-owned policy into `pack_options` are migrated
automatically when the persisted and current effective values are identical.
Conflicting legacy overrides remain forbidden.
