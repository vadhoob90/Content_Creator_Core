# Delivery plan

Tasks are ordered by dependency rather than calendar date. Each task must leave
the repository runnable and its tests green.

## WP-00: Create the new repository

Status: **implemented**

Deliverables:

- `content-creator` package and CLI skeleton
- Python packaging and development dependencies
- Repository guidance for Codex and other agent runtimes
- Offline CI
- Architecture decision records

Acceptance:

- Fresh clone installs in one documented command
- `content-creator --help` succeeds
- Unit-test and lint jobs run without provider credentials

Dependencies: none.

## WP-01: Extract the provider-neutral core

Status: **implemented**

Move and rename:

- Domain primitives not tied to posts or articles
- Provider interface and OpenAI/Anthropic adapters
- Capability-based model selector
- Agent runner
- Atomic run storage
- Generic quality-gate calculation

Do not move LinkedIn prompts, directories or format enums into the core.

Acceptance:

- Existing adapter contract tests pass unchanged
- Provider model names do not appear in orchestration code
- Core package imports contain no `linkedin`, `post` or `article` assumptions

Dependencies: WP-00.

## WP-02: Add content packs

Status: **implemented**. `general-text` runs directly; specialised packs use
single-base inheritance, protected integrity validators, isolated overlays, and
validated run overrides. The six LinkedIn routes remain regression tested.

Implement:

- Versioned `ContentPackManifest`
- Pack registry and resolver
- Pack-defined prompts, rubrics, validators and destinations
- Generic `ContentBrief`
- Directly usable, configurable `general-text` base pack
- Single-base pack extension and deterministic override rules
- LinkedIn post and LinkedIn article packs

Acceptance:

- `general-text` completes a direct end-to-end content run
- Unknown or forbidden configuration overrides fail closed
- Adding a fixture pack requires no orchestrator code change
- Existing six LinkedIn routes pass through packs
- Pack rules cannot leak into another pack

Dependencies: WP-01.

## WP-03: Add voice-domain and registry models

Status: **implemented**

Implement:

- `VoiceWorkOrder`
- `SourceRecord`
- `VoicePattern`
- `VoiceManifest`
- `VoiceApprovalReceipt`
- `VoiceRegistry`
- Voice lifecycle state machine

Acceptance:

- Invalid state transitions fail
- Candidate voices cannot resolve for content
- Voice IDs and versions are immutable after activation

Dependencies: WP-01.

## WP-04: Implement source ingestion

Status: **implemented**

Implement deterministic ingestion for:

- HTML pages
- Markdown and text
- PDF
- DOCX
- Transcript text

Capabilities:

- Metadata extraction
- Main-content extraction
- Content hashing
- Exact and near-duplicate detection
- Cache storage
- Source failure reporting

Acceptance:

- Fixture documents produce stable normalized text and hashes
- Private source content remains under `.voice-cache/`
- A failed URL does not corrupt the source index

Dependencies: WP-03.

## WP-05: Implement attribution checking

Status: **implemented**

Implement deterministic checks:

- Visible and structured bylines
- Document metadata
- Transcript speaker labels
- Person-as-author versus person-as-subject
- Co-authorship and syndication

Add `attribution-reviewer` agent only for unresolved cases.

Acceptance:

- Direct, co-authored, interview, quoted-only, third-party and uncertain
  fixtures classify correctly
- Agent review includes evidence and confidence
- Uncertain sources receive zero weight until human resolution

Dependencies: WP-04.

## WP-06: Implement corpus assessment

Status: **implemented**

Metrics:

- Usable source count and word count
- Attribution-weighted analysable word count
- Channel and content-type coverage
- Time-period diversity
- Direct versus indirect authorship
- Duplicate concentration
- Held-out allocation

Acceptance:

- The system reports supported and unsupported content packs
- A 500 attribution-weighted-word safety floor is necessary but not sufficient;
  source quality and coverage still determine confidence
- Insufficient corpora produce actionable gaps

Dependencies: WP-05.

## WP-07: Implement voice analysis and criticism

Status: **implemented**

Add:

- Voice analyst prompt and structured schema
- Independent profile critic prompt and schema
- Pattern evidence and counterexamples
- Stable, provisional and rejected statuses
- Copying and caricature warnings
- Deterministic lightweight corpus-stylistic measurements
- Separate spoken and written register summaries
- Observation, functional interpretation, contextual scope, generation guidance,
  and anti-pattern fields
- Explicit prohibition on distinctiveness claims without matched-register
  comparison

Acceptance:

- Every confirmed pattern cites multiple approved sources or explicit human
  feedback
- The critic can reject topic-specific or unsupported patterns
- No biographical fact is inferred from style

Dependencies: WP-06 and provider core.

## WP-08: Implement Voice Build

Status: **implemented**

Command:

```bash
content-creator voice build <voice-id>
```

Build:

- Profile
- Constraints
- Voice rubric
- Evaluation cases
- Learning namespace
- Candidate manifest
- Build report

Acceptance:

- Repeated builds from unchanged inputs are reproducible
- Candidate component references and hashes validate
- A failed build leaves the previous candidate and active version untouched

Dependencies: WP-07.

## WP-09: Implement voice evaluation

Status: **implemented for deterministic and candidate gates**. The bounded
live provider evaluation remains a manual release check.

Tests:

- Held-out source discrimination
- Unseen-topic transfer
- Channel fit
- Generic-draft rejection
- Caricature rejection
- Unsupported personal-context rejection
- Phrase-overlap detection
- Profile-critic consistency

Acceptance:

- Evaluation report is versioned and hashable
- Hard integrity failures cannot be averaged away
- A candidate cannot reach `awaiting_approval` without the required report

Dependencies: WP-08.

## WP-10: Implement deterministic approval and activation

Status: **implemented with a known transactional gap**

Command:

```bash
content-creator voice approve <voice-id>
```

Implement:

- Per-voice lock
- Precondition checks
- Stable version assignment
- Approval receipt
- Manifest transition
- Registry update
- Voice lock file
- Audit event
- Idempotent repeat
- Recovery after injected failure
- Deterministic deactivation and reactivation

Acceptance:

- No LLM call occurs during approval
- Repeating approval returns code 0 without mutation
- Failure before commit leaves registry unchanged
- Content resolver accepts the activated version immediately
- Deactivated voices are rejected for new runs while historical runs resolve

Current implementation note: individual registry writes are atomic and
approval commands share a per-voice lock, but candidate replacement does not
share that lock and multi-file promotion is not one transaction. Serialize
build and approval until
[#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73) is resolved.

Dependencies: WP-09.

## WP-11: Resolve voices during content creation

Status: **implemented**

Implement:

- Required `voice_id` in `ContentBrief`
- Active-version and pinned-version resolution
- Composition of core, pack and voice policy
- Immutable `resolved-context.json`
- Voice-specific writer and critic prompt inputs

Acceptance:

- Runs are reproducible from saved resolved context
- Updating a profile does not change historical runs
- Voice A cannot load Voice B’s constraints or learnings

Dependencies: WP-02 and WP-10.

## WP-12: Add profile-scoped learning

Status: **implemented**

Implement:

- Voice, pack, topic and event scope
- Active and provisional learning states
- Exact and semantic conflict surfacing
- Deduplication and supersession
- Candidate profile consolidation

Acceptance:

- Content approval updates only the selected voice
- Provisional learning does not enter prompts
- Stable profile changes require rebuild, evaluation and activation

Dependencies: WP-11.

## WP-13: Add conversational skills

Status: **implemented**

Add:

- `voice-builder` skill
- Generic `content-creator` skill
- Approval-trigger rules
- Failure and recovery instructions

Acceptance:

- “Create a voice…” starts or resumes the correct workflow
- “Approve Example Person’s voice” calls the deterministic command
- The agent cannot claim activation without successful command output
- Manual commands provide the same result if the agent is unavailable
- “Deactivate Example Person’s voice” calls the deterministic deactivation command

Dependencies: WP-10 through WP-12.

## WP-14: Complete evaluation and CI

Status: **implemented for offline and manual workflows**. Live OpenAI,
Anthropic, and ingestion runs require credentials or a public URL and must be
recorded as release evidence.

Implement:

- Shared core and provider tests
- Pack contract tests
- Voice-package contract tests
- LinkedIn regression suite
- Path-filtered offline CI
- Manual live-provider and live-ingestion evaluation

Acceptance:

- Content-only changes do not run expensive suites
- Profile changes run provenance, isolation, overlap and voice evaluations
- Live-provider evaluation is manual and bounded

Dependencies: all implementation tasks.

## WP-15: Documentation and release

Status: **implemented**

Deliver:

- Quick start
- Voice creation guide
- Content-pack authoring guide
- Provider guide
- Privacy and source-handling guide
- Migration guide
- Troubleshooting and recovery commands

Acceptance:

- Every documented command is exercised in tests
- A new user can create, approve and use a fixture voice from a fresh clone

Dependencies: WP-14.

## WP-16: Add optional perspective provenance

Status: **implemented**

Implement:

- Perspective contexts owned by a voice identity
- No implicit cross-context inheritance
- Provenance, qualifications, counterpositions, confidence, and lifecycle state
- Deterministic candidate verification, approval, versioning, retirement, and
  deactivation
- Optional perspective and author-contribution fields in work orders
- Exact perspective version and component hashes in resolved run context
- Claim-provenance run artifact
- Research, writer, and critic perspective boundaries
- Publication-generated proposals that never update an active perspective
- Explicit proposal staging and approval

Acceptance:

- A voice can run without a perspective
- Two contexts for one person cannot load or update one another
- Perspective is never treated as factual authority
- Unsupported first-person positions fail validation
- Publication creates only context-local candidates
- Perspective changes require deterministic approval
- Historical runs resolve their pinned perspective version
- OpenAI and Anthropic receive the same normalized perspective contract

Dependencies: WP-11, WP-12, and WP-15.
