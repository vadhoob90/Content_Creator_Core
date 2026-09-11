# ADR 0016: Author-edit adoption and draft-bound claim review

- Status: Accepted for implementation
- Date: 2026-09-11
- Scope: Author-edit integrity slice of #135

## Context

The existing revision operation preserves diffs but requires model critique and
only appends provenance history. Direct edits can leave prior claims and review
results attached to different bytes. Refreshing production metadata also
resolves currently installed pack policy, which cannot establish historical
validation inputs.

## Decision

Introduce a provider-free author-edit application boundary, exact accepted text
snapshots, and a versioned draft-integrity record binding text and research
hashes to author claim decisions. Only trailing-newline changes may preserve
claim clearance automatically. Other changes require explicit review; a model
critique is not authority to carry forward factual approval.

Generation captures effective pack inputs and their digest. Adoption validates
against this snapshot and preserves the original voice/context references.
Missing historical evidence is an explicit recovery condition. Model quality
scores remain historical when no new critic was invoked.

Keep snapshot capture and manifest refresh composed above low-level storage.
Storage gains an exact-byte atomic writer; its existing newline-appending text
writer retains its behavior. Domain state adds an optional claim-review flag,
with coordinator actions directing authors to exact evidence.

Serialize author adoption, claim approval, ordinary revision, and publication
through a shared per-run lock. Adoption and claim approval journal touched
artifacts, compensate write failures, and block further mutations/publication
after interruption until explicit recovery. These are application-level
recovery guarantees, not a claim that multiple filesystem writes form one OS
transaction or that external editors obey Core's lock.

Move existing publication coordination into the publication lifecycle so the
orchestrator remains a small locked entry point and stays within architecture
limits. Existing public operation signatures remain available.

## Compatibility

Add `adopt-edit`, `approve-edit-claims`, and `recover-edit` commands. Add draft
integrity and claim-review schemas at version 1.0, with unknown versions rejected.
Existing work-order, state, and production fields remain readable. Absence of
new evidence does not invent retrospective approval; available legacy final
hashes are checked before publication.

Existing `revise` still invokes the writer/critic as requested. Changed wording
now conservatively leaves claims for author review, and stale final/research
bytes cannot inherit approval at publication. This is deliberate provenance
hardening and must be called out in release notes.

## Consequences

Authors can adopt edits without spending provider allowance or editing hashes
manually. Conservative review can require a decision for harmless stylistic
changes. Local snapshots/journals retain private text and remain inside ignored
run evidence. Automatic claim understanding, visual slots, bundles, and draft
export are not implemented by this decision.
