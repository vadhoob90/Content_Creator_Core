# Learning and publication

The instruction to move a reviewed piece to `published/` is the approval
trigger. Before the move, Core checks deferred operational diagnostics across
the piece's content lineage. If an eligible Core support candidate exists,
publication pauses once for a `publish-only` or `prepare-issue` decision. See
[Runtime diagnostics and Core support candidates](runtime-diagnostics.md).

After that pre-publication decision, the application:

1. Resolves `final.md` for the specified run
2. Refuses to overwrite an existing target
3. Revalidates deterministic perspective provenance against the exact final
   bytes and pinned immutable context
4. Records `assessment.json` and the publication perspective evaluation
5. Calls the learning and perspective extractors
6. Writes the piece to the selected pack's configured repository destination
7. Writes a privacy-safe tracked publication receipt
8. Adds deduplicated records to
   `profiles/<voice-id>/learnings/memory.json`

The destination is untouched when provenance fails. See
[Publication provenance and CI verification](publication-provenance.md) for
receipt policy, legacy migration, and the offline CI command.

This is repository publication only. It never posts to LinkedIn and never
commits or pushes.

Specific author feedback can support an `active` learning. Patterns inferred
only from publication or draft differences remain `provisional`. The extractor
assigns that status from its evidence; storage does not promote every candidate
merely because some feedback was supplied.

Active structured learnings are added to later role prompts. Provisional
entries remain recorded but inactive. `profiles/<voice-id>/voice.md` is not rewritten
automatically; consolidation requires a deliberate, reviewed repository change.

Learning roles are schema-constrained to the prompt consumers `researcher`,
`writer`, and `critic`. Unsupported extractor output, including `author`, is
rejected and recorded as a visible `learning_update_failed` publication event.
For compatibility, a legacy unsupported record may remain stored when it is
provisional or rejected. A legacy unsupported `active` record stops prompt
assembly with its record id and remediation: map it deliberately to a supported
role, or mark it provisional/rejected for author review. It is never silently
left active without a consumer.

Repository-wide principles live separately in `learnings/memory.json`. They
apply across voices in that content repository. Publication does not promote a
voice learning into repository memory automatically; cross-voice promotion is
a deliberate human-reviewed policy change.

If extraction fails, publication is retained and the run records a
`learning_update_failed` event. This prevents a model outage from losing an
already approved piece.

## Add feedback without publishing again

Durable feedback can arrive after repository publication or after a reviewed
draft receives later author edits. Apply that feedback directly to the run's
selected voice without writing to the content pack destination:

```bash
content-creator learn <run-id> \
  --feedback "Prefer the concrete operational consequence before abstraction." \
  --idempotency-key post-publication-feedback-1
```

`learn` accepts runs in `ready`, `needs_author`, or `published` state. It loads
the persisted `final.md`, resolves the original content pack, and verifies the
exact persisted voice version against its active manifest and component
hashes. A missing, inactive, placeholder, or tampered voice fails before memory
is changed.

Each attempt preserves a hashed `learning-request-*.json`, a versioned
`learning-assessment-NN.json`, and a versioned
`learning-extraction-NN.json` under the original run. The run receives visible
`learning_update_started`, `learning_update_completed`, or
`learning_update_failed` events. Existing publication files are never opened
for writing by this operation.

Reuse the same idempotency key only for the same run and feedback. A completed
retry returns without invoking the extractor or applying memory again. Reusing
the key with different feedback fails; intentional new feedback needs a new
key. Unkeyed requests remain supported, but retry-capable hosts should always
supply a stable key.
