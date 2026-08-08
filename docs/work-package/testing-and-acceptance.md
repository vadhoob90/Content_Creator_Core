# Testing and acceptance

Software tests establish correctness. Evaluations establish whether an LLM
output satisfies evidence-backed quality and voice criteria. Both are required.

## Implementation status

The offline software, fixture-integration, pack, voice-lifecycle, ingestion,
attribution, overlap, route replay, documentation-command, and isolation suites
are implemented. Offline CI never calls a paid model and intentionally ignores
ordinary files under `content/**` and publication-triggered learning updates.

The repository also contains manually triggered workflows for bounded OpenAI,
Anthropic, and live URL-ingestion evaluation. A release is not complete until
those workflows have been run successfully in the target GitHub environment;
their results cannot be manufactured by the offline harness.

## Unit tests

### Core

- Provider request translation
- Capability selection and tie-breaking
- Schema parsing and invalid output
- Atomic storage
- Quality-gate calculation
- State transitions

### Packs

- Manifest validation
- Resolver precedence
- General-text default and override resolution
- Forbidden override rejection
- Single-base inheritance
- Integrity-validator preservation
- Validator isolation
- Destination resolution
- Research-route composition

### Voices

- Voice ID normalization
- Manifest and component hashes
- Registry lookups
- Active and candidate resolution
- Approval receipt schema
- Learning isolation

### Ingestion

- HTML main-text extraction
- PDF and DOCX extraction
- Transcript speaker selection
- Exact and near-duplicate detection
- Cache exclusion from Git
- Partial source failure

### Attribution

- Direct authorship
- Co-authorship
- Interview
- Quoted-only content
- Third-party content
- Conflicting metadata
- Human override

## Deterministic integration tests

Use fixtures and a scripted fake provider.

### Voice build

1. Create work order
2. Ingest fixture sources
3. Attribute sources
4. Assess corpus
5. Return scripted analysis
6. Return scripted criticism
7. Compile candidate
8. Run fixture evaluations
9. Reach `awaiting_approval`

### Activation

- Successful activation
- Repeat activation
- Missing authorisation
- Invalid manifest
- Missing evaluation
- Failed evaluation
- Permitted editorial override
- Forbidden integrity override
- Registry write failure
- Recovery and retry
- Concurrent activation lock
- Candidate replacement between validation and promotion fails closed
- Partial promotion does not allocate an immutable numeric version
- Deactivation
- Attempted use after deactivation
- Reactivation with a new approval receipt

The candidate-replacement and partial-promotion cases are target acceptance
coverage, not current guarantees. Their implementation is tracked in
[#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73).

### Content use

- Candidate voice rejected
- Unknown voice rejected
- Active voice selected
- Explicit version selected
- Superseded version remains reproducible
- Voice and pack rubrics compose
- Historical context remains immutable

### Learning

- Explicit correction becomes active
- Inferred change remains provisional
- Duplicate is ignored
- Conflict is surfaced
- Voice isolation is preserved
- Profile consolidation creates a candidate rather than editing active state

### Perspective provenance

- Empty and populated perspective contexts
- Candidate verification and idempotent activation
- Two isolated contexts owned by one voice
- Optional runs with no perspective
- Exact active and pinned version resolution
- Component tamper rejection
- Context deactivation and historical resolution
- Unsupported first-person position rejection
- Author-contribution provenance
- Perspective treated as position rather than factual authority
- Publication proposal creation without active mutation
- Proposal deduplication and explicit staging
- Qualification, supersession, retirement, and version history
- Equivalent OpenAI and Anthropic request contracts
- Blind A/B packet creation against an ordinary-chat baseline
- Structured capture of voice authenticity, originality, factual reliability,
  publishability, revision effort, and author preference

## Evaluation suites

### Voice construction

- Confirmed patterns have source support
- Profile critic finds planted unsupported rules
- Channel confidence reflects corpus coverage
- Held-out allocation is excluded from analysis
- Linguistic measurements are deterministic and attribution weighted
- Spoken and written registers remain separately inspectable
- Speaker-labelled transcripts exclude interviewer turns
- Numerical ranges remain descriptive rather than mandatory generation targets
- Features are not called distinctive without a matched-register baseline

### Generated content

- Voice similarity without phrase copying
- Naturalness rather than mannerism stacking
- Unseen-topic transfer
- Correct channel adaptation
- Personal and biographical integrity
- Generic draft rejection
- Caricature rejection

### Phrase overlap

Deterministic checks compare generated content with the normalized corpus:

- Exact sentence overlap
- Long n-gram overlap
- Unusually distinctive phrase overlap
- Quotation use and attribution

Hard overlap thresholds fail the run or require explicit quotation treatment.

## Human evaluation

The profile owner or authorised reviewer assesses:

- “Could I plausibly approve this?”
- “Which passages do not sound like me?”
- “Does this exaggerate a habit?”
- “Has it introduced an experience I did not provide?”
- “Is this appropriate for the intended channel?”

Feedback is stored as structured events with voice, version, pack and run IDs.

## CI matrix

| Changed area | Required checks |
|---|---|
| Core code | Full unit, integration and replay suite |
| Provider adapter | Shared provider contract suite |
| Content pack | Core plus that pack’s routes and evaluations |
| Voice profile | Schema, provenance, overlap, isolation and voice replay |
| Perspective profile | Schema, provenance, context isolation, lifecycle and prompt compilation |
| Perspective proposal queue | No automatic workflow; proposals arise from ordinary publication and remain inactive |
| Learning memory | No automatic workflow; local schema, provenance, conflict and prompt compilation |
| Content artifacts only | No automatic workflow; ordinary writing must not start CI |
| Documentation | Link, command and example validation |

No automatic CI job calls a paid model or external search service.
Publishing a piece or updating its incremental learning memory does not start
CI. Those checks run locally and whenever engine, test, pack, profile, or
workflow code changes.

## Non-functional acceptance

- A build is resumable after a source or provider failure
- Activation is atomic and idempotent
- Logs do not expose private source text or credentials
- Repeated deterministic fixture runs produce identical manifests and hashes
- Every content run identifies its pack, voice, and optional perspective versions
- No command silently overwrites active profiles or final content
- A manual recovery command exists for every conversational action

## Definition of done

The complete programme is done when:

1. A fresh clone installs successfully using the documented command
2. A fixture voice is created from URL, PDF, DOCX and transcript inputs
3. Ambiguous attribution is surfaced rather than guessed
4. The candidate package includes profile, constraints, rubric, sources,
   evaluations and isolated learnings
5. The candidate cannot generate content
6. `voice approve` activates it without an LLM call
7. Repeating approval is a successful no-op
8. An active voice produces content through the LinkedIn pack
9. The configurable general-text pack completes an end-to-end run
10. A specialised pack extends general-text without weakening integrity gates
11. The run snapshots all resolved versions and hashes
12. Content approval updates only the correct learning namespace
13. A profile update creates and evaluates a new candidate version
14. Voice deactivation prevents future use without deleting historical evidence
15. The current LinkedIn route and provider suites pass in the new repository
16. Offline CI is green
17. Manual Anthropic and OpenAI flagship evaluations complete successfully
18. Documentation commands are exercised by automated tests
19. Multiple perspective contexts for one author remain isolated
20. Publication can propose but cannot activate a perspective change
