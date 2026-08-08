# Final design review

## Review outcome

Implemented in the Content Creator repository, subject to the manual live
provider and ingestion release checks in this work package.

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
- Optional author perspectives are versioned separately from voice
- Perspective contexts do not inherit or update one another
- Publication can propose but cannot activate a perspective change
- The current LinkedIn repository remains the regression baseline

The implementation review predates the candidate-promotion race audit. Registry
files are replaced atomically, but voice and perspective candidate replacement
and multi-file promotion are not yet a single transaction. Operators must
serialize staging and approval while
[#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73) remains open.

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

### Added perspective provenance

The original design conflated authentic expression with authentic thought.
Perspective is now an optional, context-isolated package owned by a voice
identity but versioned independently. Author positions carry provenance,
qualifications and counterpositions; research may challenge them but cannot
become them. Publication creates proposals only, and deterministic author
approval is required before reuse.

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

## Delivered implementation slice

The implementation builds through WP-10 using:

- One fixture voice corpus
- HTML, PDF, DOCX and transcript fixtures
- Configurable `general-text` as the base and first directly usable pack
- A fixture specialised pack followed by LinkedIn post
- Fake-provider evaluation
- Deterministic approval, deactivation and recovery

LinkedIn article and direct `general-text` are also executable. Personal source
material from LinkedIn Writer was deliberately not migrated; each real voice
must enter through the authorised build and approval lifecycle.

## Final recommendation

Use this repository as the generic engine and keep LinkedIn Writer as the
behavioural baseline. Record bounded OpenAI, Anthropic, and live-ingestion
workflow results before declaring a production release.
