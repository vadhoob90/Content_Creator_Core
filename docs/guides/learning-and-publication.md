# Learning and publication

The instruction to move a reviewed piece to `published/` is the approval
trigger. Before the move, Core checks deferred operational diagnostics across
the piece's content lineage. If an eligible Core support candidate exists,
publication pauses once for a `publish-only` or `prepare-issue` decision. See
[Runtime diagnostics and Core support candidates](runtime-diagnostics.md).

After that pre-publication decision, the application:

1. Resolves `final.md` for the specified run
2. Refuses to overwrite an existing target
3. Writes the piece to the selected pack's configured repository destination
4. Records `assessment.json`
5. Calls the learning extractor
6. Adds deduplicated records to
   `profiles/<voice-id>/learnings/memory.json`

This is repository publication only. It never posts to LinkedIn and never
commits or pushes.

Specific author feedback can support an `active` learning. Patterns inferred
only from publication or draft differences remain `provisional`. The extractor
assigns that status from its evidence; storage does not promote every candidate
merely because some feedback was supplied.

Active structured learnings are added to later role prompts. Provisional
entries remain recorded but inactive. `profiles/<voice-id>/voice.md` is not rewritten
automatically; consolidation requires a deliberate, reviewed repository change.

Repository-wide principles live separately in `learnings/memory.json`. They
apply across voices in that content repository. Publication does not promote a
voice learning into repository memory automatically; cross-voice promotion is
a deliberate human-reviewed policy change.

If extraction fails, publication is retained and the run records a
`learning_update_failed` event. This prevents a model outage from losing an
already approved piece.
