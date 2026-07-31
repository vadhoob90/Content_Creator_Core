# Changelog

All notable changes to Content Creator are documented here.

The project follows semantic versioning. Entries marked **Unreleased** are
present on the development branch but are not available from an immutable
release tag.

## [Unreleased]

## [0.10.0] - 2026-07-31

### Added

- Pack-owned `statistical_voice_score.eligible` policy so automatic draft
  scoring is explicitly limited to content formats with sufficiently stable
  evidence.
- Regression coverage proving that ineligible packs create no statistical
  score artifact and supply no score to the critic, even when workspace and
  voice preferences enable scoring.

### Changed

- Automatic statistical scoring now requires both voice or workspace opt-in
  and explicit content-pack eligibility. The built-in `linkedin-article` pack
  is eligible; `linkedin-post` and mixed-format `general-text` remain fail-safe
  off.
- Documentation now distinguishes automatic workflow scoring from the
  explicit `voice score` command, which remains available for deliberate,
  ad hoc assessment of any sufficiently long text.

### Migration

- Existing and custom packs default to ineligible when the new field is
  absent. Pack authors must add
  `"statistical_voice_score": {"eligible": true}` only after validating that
  the pack's content length and reference evidence support stable comparison.
- No stored-run or voice migration is required. Explicit offline scoring is
  unchanged.

## [0.9.0] - 2026-07-31

### Added

- A unified, voice-scoped `statistical_voice_score` with deterministic and ML
  methods, explicit voice-creation selection, on-demand `voice score`, and
  later `voice score-config` controls. Both methods report a 0–100 score with
  method, reliability, evidence coverage, observations, and claim limits.
- Deterministic scoring that penalises only distance beyond robust
  interquartile-range envelopes, so drafts cannot improve their score merely
  by moving closer to the historical corpus centre.
- Optional, default-off draft comparison against an active voice's linguistic
  distribution. Enabled runs preserve a per-revision advisory artifact and
  expose material outliers only to the critic, without changing deterministic
  validation or quality-gate calculations.
- Explicit offline deterministic scoring through
  `content-creator voice score <voice-id> --draft <path> --method deterministic`,
  including minimum evidence gates and no authorship or identity claim.
- Explicit, optional regularised logistic-regression training from an active
  voice and matched non-author documents. Reliability preflight refuses
  unusable corpora, pauses on low-confidence data, and requires an explicit
  override before training; training never activates ML assessment.
- Version-scoped, author-workspace JSON model artifacts and dependency-free
  inference. Raw corpus text, local paths, and unsafe pickle payloads are not
  persisted in the model.

### Changed

- Automatic score artifacts and critic payloads now use the common
  `statistical_voice_score` name. The score remains critic-only advisory
  evidence with no direct rubric weight, validation effect, or publication
  gate.

### Migration

- Existing workspaces remain default-off. The pre-release `voice_assessment`
  configuration is accepted as a compatibility alias, while new workspaces use
  `statistical_voice_score` with `method: deterministic` or `method: ml`.
- Existing voices without a voice-scoped preference continue to use the
  workspace default. Creating or onboarding a new source-derived voice records
  an explicit disabled, deterministic, or ML preference.

## [0.8.0] - 2026-07-31

### Added

- Atomic, workspace-local idempotent run submission through
  `--idempotency-key`, hashed key storage, canonical work-order fingerprints,
  duplicate reuse, conflict rejection, and read-only submission lookup.

### Fixed

- Supplied research is now loaded and validated during preflight, before a
  normal run is allocated. Missing, malformed, or internally inconsistent
  briefs produce a separate invocation diagnostic rather than a failed content
  run.
- Prior critique issues now use a typed machine disposition with a separate
  explanatory note. Legacy free-form statuses are normalised fail-safe so
  explanatory `resolved` and `author_rejected` values no longer cause false
  quality-gate failures.
- Active voice prompts now declare the resolved version manifest as lifecycle
  authority and remove stale candidate-only claims from historical profile
  prose. Newly built profiles are lifecycle-neutral.

### Migration

- No stored-run or workspace migration is required. Retry-capable hosts should
  pass a stable `--idempotency-key` for the same logical submission and use a
  new key with `--parent-run` for an intentional revision. Existing callers
  that omit the key retain the previous run behavior.
- Invalid supplied-research inputs now appear under invocation diagnostics
  rather than as failed normal runs, so operational tooling should inspect
  `.content-creator/invocations/` when preflight rejects an input.

## [0.7.0] - 2026-07-31

### Added

- Fail-safe, workspace-local runtime diagnostic journals, sanitised summaries,
  deterministic issue fingerprints, and Core support candidates.
- Bounded retry recording for invalid structured output and narrowly
  classified transient provider failures.
- Content lineage through `content_session_id`, `parent_run_id`, and the
  `--parent-run` revision option.
- A one-time pre-publication diagnostic decision with `publish-only` and
  `prepare-issue` outcomes, plus issue-link lifecycle recording.
- Immediate support candidates for fatal Core failures and invocation
  diagnostics for failures that occur before a run is created.

### Changed

- Linked the PyPI package from the main README, reframed the chat-app
  comparison in neutral terms, and documented the complete maintainer release
  and downstream-upgrade process.
- Coordinator actions and packaged host instructions now defer recovered
  diagnostics during editorial iteration and surface them once at publication.
- Workspaces ignore local invocation diagnostics and generated workspaces
  include bounded diagnostic policy defaults.

### Migration

- Existing workspaces receive safe diagnostic defaults without a configuration
  change. Hosts should handle publish exit code `4` by presenting the returned
  support candidate and repeating publication with `--diagnostic-decision`.
- Hosts should pass `--parent-run <run-id>` when a new run revises an existing
  piece so diagnostics aggregate across the complete editorial lineage.

## [0.6.0] - 2026-07-30

### Added

- Human-readable `overview` and guided, non-mutating `start` entry points.
- Typed coordinator workspace, provider, voice, run, warning, and recommended
  action state.
- Preview-first, immutable workspace dependency upgrades with validation and
  rollback.
- A task-oriented documentation index and registry-distribution release ADR.
- A validated, tag-driven PyPI release workflow using Trusted Publishing.
- A left-to-right repository workflow diagram for authors and maintainers.

### Changed

- Default help emphasizes the author command surface while preserving advanced
  command families and all existing CLI invocations.
- Offline doctor checks are reusable by the coordinator and overview.

## [0.5.0] - 2026-07-29

### Added

- A deterministic Content Creator Coordinator interface for agent hosts.
- Machine-readable workspace context, capability, run-list, and next-action
  commands.
- Workspace-scoped coordinator defaults that reduce repetitive questions
  without overriding explicit author choices.
- Packaged Content Creator and Voice Builder skills in generated workspaces.
- Whole-workspace voice verification through `voice verify-all`.

### Changed

- Generated repository guidance now begins from persisted coordinator context.
- Voice onboarding guidance distinguishes a stylistically different voice from
  a subject-matter perspective.

## [0.4.0] - 2026-07-29

### Added

- Thin author-workspace generation through `content-creator workspace create`.
- Explicit starter versus source-derived voice onboarding.
- The versioned Clear Professional Starter for authors without prior writing.
- Automatic perspective disabling while a starter voice is active.
- Automatic perspective catalogue resolution for approved source-derived
  voices.
- Recursive ingestion from external local writing directories.
- Persisted provider selection through `content-creator provider select`.
- A workspace-first landing README and separate Core development README.

### Changed

- Core no longer silently defaults to a metered API provider.
- Local file paths are removed from versioned voice source indexes.
- Generated workspaces ignore uploaded voice documents and operational voice
  work orders while retaining public URL inventories.
- Local author documents can be attested directly without publication or
  public attribution.
- README and repository references use the current Core and downstream names.

### Compatibility

- Existing approved v0.3 voice manifests remain readable because new manifest
  fields have backward-compatible defaults.
- Existing workspaces must select a provider explicitly or continue supplying
  `CONTENT_CREATOR_PROVIDER`.
- Existing active voices do not need starter onboarding.
- See [Migrating to v0.4](docs/guides/migrating-to-v0.4.md).

## [0.3.0]

- Added repository-owned agent architecture and versioned workspace
  dependencies.

## [0.2.0]

- Added the workspace-oriented provider-neutral Core.
