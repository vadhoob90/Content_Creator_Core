# Final design review

## Review outcome

Ready for implementation as a new repository, subject to the scope and gates in
this work package.

The proposal is internally coherent:

- Provider selection is separate from content and voice policy
- The orchestrator is deterministic
- Content types are packs rather than core branches
- `general-text` is a directly usable configurable base for specialised packs
- A voice is a versioned package rather than a person-specific agent fork
- Candidate construction and active use are separate
- Approval and activation use an idempotent deterministic command
- Every content run snapshots exact resolved dependencies
- Learning is isolated by voice and cannot rewrite an active profile directly
- The current LinkedIn repository remains the regression baseline

## Amendments made during final review

### Simplified creation path

The original command sequence required `voice create` followed by `voice
build`. The user-facing default now runs creation through evaluation and stops
at human approval. The separate build command remains available for recovery,
testing and automation.

### Named request structuring “briefing”

The proposed generic repository uses `content-briefing` and `voice-briefing`.
This describes the value more clearly and avoids duplicating a briefing agent
with a differently named planner. Deterministic extraction still bypasses the
model when the request is already explicit.

### Added deactivation

The earlier lifecycle could activate and supersede a voice but did not handle
withdrawn permission or a changed intended use. The design now includes
deterministic deactivation, reapproval and tests that preserve historical runs
while blocking future use.

### Clarified authorisation

The tool records the user’s attestation and scope; it does not independently
verify legal identity or authority. Authorisation, expiry and revocation are
explicit data. These are non-overridable activation gates.

### Added source-use and retention metadata

Source records now capture why material may be analysed and whether the system
retains full local text or only metadata and hashes.

### Clarified evaluation thresholds

Numeric scores shown in examples are illustrative. Required thresholds belong
in versioned evaluation policy, not application code. Personal integrity,
authorisation, provenance and material phrase overlap remain hard gates.

## Critical risks that remain

### Voice quality cannot be proven automatically

Held-out and judge-model evaluations are useful but cannot establish that a
person feels represented. The authorised human review remains essential.

### Attribution remains evidential, not forensic

Bylines, metadata and linguistic analysis cannot prove who physically drafted a
document. Ambiguity must be visible and human-resolved.

### Generic-engine pressure

Supporting too many media types would weaken the design. The first release
remains text-only and must prove at least two genuinely different content packs.

### Evaluation cost and drift

Offline fixtures test behaviour, not current model quality. Live provider
evaluation remains manual, bounded and recorded by model version.

### Private-source handling

Ignored local caches reduce accidental commits but are not a full secrets or
records-management system. Enterprise use would require an approved encrypted
store, retention policy and access controls.

## Decisions intentionally deferred

- External CMS and social-network distribution
- Multi-user authentication and role-based access
- Encrypted shared corpus storage
- Fine-tuning
- Non-text asset generation
- Automated pricing-based model optimisation
- Central hosted service

These are not required to prove the architecture.

## Recommended first implementation slice

Build through WP-10 using:

- One fixture voice corpus
- HTML, PDF, DOCX and transcript fixtures
- Configurable `general-text` as the base and first directly usable pack
- A fixture specialised pack followed by LinkedIn post
- Fake-provider evaluation
- Deterministic approval, deactivation and recovery

Then add LinkedIn article, migrate Bharath’s profile and prove a second
non-LinkedIn content pack. This sequence tests the two most important
abstractions before expanding scope.

## Final recommendation

Proceed with a new repository. Do not modify LinkedIn Writer into the generic
engine in place. Use this repository as the behavioural baseline and migrate
only after the new core, voice lifecycle and LinkedIn pack pass the defined
acceptance suite.
