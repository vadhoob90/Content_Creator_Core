# Runtime diagnostics and Core support candidates

Content Creator records operational failures separately from editorial
learning. Voice, writing, and research learning can influence later agent
prompts. Runtime diagnostics never enter those prompts and never change Core
automatically.

## Workspace and Core boundary

The installed `content-creator` package executes the reusable engine. The
author repository remains the workspace, so its run evidence is written under
that repository's `runs/<run-id>/` directory. Diagnostics do not write into a
Core source checkout.

Each run may contain:

- `diagnostics.jsonl`, the append-only attempt and failure events;
- `diagnostic-summary.json`, the consolidated safe summary;
- `support-candidate.json`, the machine-readable Core issue candidates; and
- `support-candidate.md`, the corresponding human-readable report.

Diagnostics are fail-safe. An inability to record an event must not become the
reason content generation fails.

## What is recorded

Core records agent-call starts, completions, failures, retry decisions,
recovery outcomes, provider/model selection, phase, role, attempt, and elapsed
time. Details are sanitised before persistence. Candidate reports exclude
drafts, prompts, credentials, absolute workspace paths, and provider payloads.

Classification keeps ownership explicit:

- `core` for structured-output, orchestration, storage, and unexpected engine
  failures;
- `provider` for provider availability or service failures;
- `workspace_configuration` for authentication, installation, routing, or
  configuration problems; and
- ordinary editorial validation remains in revision artifacts rather than
  becoming a support candidate.

Only an eligible `core` classification creates a Core support candidate.

## Retry policy

Core makes at most one additional attempt for invalid structured agent output
and narrowly recognised transient provider failures. Every attempt remains in
the diagnostic journal. Unknown, authentication, installation, and
configuration failures are not retried.

The workspace policy may reduce attempts or disable recording:

```yaml
diagnostics:
  enabled: true
  max_attempts: 2
  defer_recovered_until_publication: true
```

`max_attempts` accepts `1` through `3`. Deferred presentation is a safety
invariant and cannot be disabled through workspace configuration.

## Draft iteration and content lineage

Every work order receives a `content_session_id`. A later run that revises the
same piece should name its parent:

```bash
content-creator --workspace . run \
  "Revise the opening and preserve the argument" \
  --parent-run <prior-run-id> \
  --pack linkedin-post \
  --voice <voice-id> \
  --research none
```

Core carries the parent's content session and reviewed draft into the new run.
The writer receives the parent text as a structured revision baseline with an
explicit instruction to preserve unaffected approved passages. At publication
Core collects unresolved diagnostics across the whole lineage, groups
identical fingerprints, and reports the occurrence count once.

## Deferred publication boundary

Recovered diagnostics remain silent while the author iterates. When the author
approves repository-local publication, the host calls the normal command:

```bash
content-creator --workspace . publish <run-id>
```

With no eligible candidate, publication proceeds normally. When a deferred
candidate exists, the command performs no publication and returns exit code
`4` with:

```json
{
  "status": "awaiting_diagnostic_decision",
  "requires_diagnostic_decision": true,
  "diagnostic_summary": "runs/<run-id>/diagnostic-summary.json",
  "support_candidate": "runs/<run-id>/support-candidate.json"
}
```

The host presents that report once and asks the author to choose. Publish
without preparing an issue:

```bash
content-creator --workspace . publish <run-id> \
  --diagnostic-decision publish-only
```

Or publish while preserving a request for the host to prepare a Core issue:

```bash
content-creator --workspace . publish <run-id> \
  --diagnostic-decision prepare-issue
```

These choices govern the diagnostic candidate, not the content. A GitHub
failure must not undo repository publication.

## Fatal failures

A fatal Core failure has no publication boundary, so Core generates its
support candidate immediately. `coordinator next-actions <run-id>` exposes the
fatal diagnostic for the host to present alongside the failure explanation.
Provider and workspace-configuration failures remain actionable diagnostics
without being misreported as Core defects.

Failures before a run can be created are preserved under:

```text
.content-creator/invocations/<invocation-id>/diagnostics.jsonl
```

## External issue submission

Core does not hold GitHub credentials, search for duplicates, or submit
issues. An authenticated host may search the configured Core repository, show
the sanitised draft, and require explicit approval before creating or updating
an issue.

After submission, record the relationship:

```bash
content-creator --workspace . diagnostics link-issue <run-id> \
  --issue-url https://github.com/<owner>/<repository>/issues/<number>
```

The candidate then becomes `issue_raised` and does not resurface. A
`publish-only` decision marks it `dismissed`. Candidate evidence otherwise
remains workspace-local.
