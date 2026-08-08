# Changelog

All notable changes to Content Creator are documented here.

The project follows semantic versioning. Entries marked **Unreleased** are
present on the development branch but are not available from an immutable
release tag.

## [Unreleased]

### Added

- Independent branch-coverage measurement and a 71% baseline ratchet, while
  preserving the existing 88% statement-coverage guarantee and separate route
  matrix evaluation.

### Changed

- CI and the complete local gate now report partial branches and enforce
  statement and branch thresholds independently.

## [1.8.0] - 2026-08-08

### Added

- A versioned `production-manifest.json` for every new content run, unifying
  content pack, voice, perspective, research, model-routing, lineage, revision,
  artifact-hash, and publication metadata without copying private inputs.
- A compact `production-manifest.md` table and `review.md` copy that place
  production details above reviewed content while preserving clean `final.md`
  and published files.

### Changed

- Production metadata now refreshes at every persisted run-state transition,
  including checkpoints, failures, revisions, and publication.
- Production metadata refresh is composed at the application boundary so
  low-level storage remains independent of manifests, packs, and context
  composition. CI now rejects every internal import edge involved in a cycle.
- New publication receipts record the resolved content pack ID and version in
  addition to pinned voice and perspective evidence.

### Migration

- No stored-data migration is required. Existing runs remain unchanged when
  read; their next deliberate state-saving operation backfills a manifest from
  available evidence without inventing missing historical model context.

## [1.7.0] - 2026-08-08

### Added

- Advisory architecture telemetry for single-importer modules and cross-file
  inheritance, with characterized composition rules for orchestration, voice
  building, and workspace generation.
- Executable custom-provider and custom-stage examples, an extension guide,
  maintainer module maps, and explicit `FakeProvider` testing guidance.
- Property-based attribution and publication-path tests using the locked
  Hypothesis dependency.

### Changed

- Orchestration, voice building, and workspace scaffolding now compose focused
  collaborators instead of splitting implementations through inheritance.
- Voice-build and voice-ML implementation clusters are cohesive packages;
  corpus policy now lives with voice building and phrase-overlap policy lives
  beside voice evaluation. Stable `voice_builder` and `voice_ml` imports remain
  unchanged.
- Post-publication perspective extraction and learning assessment now have
  focused services, shortening the orchestrator's normal reading path.

- CI and release automation now install from the frozen lockfile, audit known
  vulnerabilities across the supported Python range boundaries, enforce
  readability checks, reject release tags outside `main`, and publish SBOM and
  provenance attestations with reproducibly built artifacts.

### Migration

- No CLI, persisted-data, or generated-workspace migration is required. Internal
  flat implementation modules were never supported import paths; consumers
  should continue using `content_creator.voice_builder` and
  `content_creator.voice_ml`.

## [1.6.0] - 2026-08-08

### Added

- Privacy-safe `context-composition.json` manifests for every persisted agent
  invocation, including ordered loaded and skipped sources, hashes, versions,
  selected learning and perspective record IDs, model routing, and hashed task
  input references.
- A read-only `personalisation explain --role <role>` preflight, historical
  `context show <run-id>` inspection, and opt-in `run --show-context` loading
  trace on standard error.
- A runtime context composition guide in Core and a concise equivalent page in
  every newly generated author workspace.

### Changed

- Prompt assembly now returns composition provenance alongside the unchanged
  provider prompt, making voice-scoped learning and all other runtime layers
  directly auditable.
- Generated workspace navigation and the packaged content-creator skill now
  signpost preflight, live, and historical context inspection.

### Migration

- No stored-data migration is required. Existing runs remain readable but do
  not gain retrospective composition evidence; runs created with v1.6.0 record
  the new artifact automatically.
- Existing customised workspace documentation remains untouched. Fresh
  workspaces receive `docs/runtime-context.md`; existing authors can use the
  commands immediately after upgrading Core.

## [1.5.0] - 2026-08-08

### Added

- An author-facing `personalisation show` command that explains each agent,
  identifies customised agent files, shows actual active repository and
  voice-scoped learning, and links voice and perspective state to direct paths.
- Hash-anchored `voice reject` decisions with immutable rejection snapshots and
  receipts, while preserving the currently active voice version.
- Author-first navigation in newly generated workspaces, including a concise
  quick start, personalisation guide, profile and learning indexes, and a
  separate technical setup and `uv` guide.

### Changed

- Candidate status now distinguishes pending review, already-active candidates,
  rejected candidates, and invalid candidates instead of treating directory
  presence as an unresolved decision.
- Candidate build publication, approval, and rejection share one per-voice
  lifecycle lock so a reviewed hash cannot change during a decision.
- The Core release policy now includes a decision table for borderline semantic
  versioning cases, including stricter validation, error contracts, security
  hardening, dependencies, and experimental interfaces.

### Migration

- No stored-data migration is required. After upgrading, run
  `content-creator --workspace . personalisation show` to inspect effective
  agent, learning, voice, and perspective state.
- Existing customised READMEs remain untouched. Fresh workspaces receive the
  author-first navigation automatically; existing workspaces can add the links
  from the upgrade preview deliberately.

## [1.4.1] - 2026-08-08

### Changed

- Documentation now distinguishes v1.4.0's atomic candidate-build replacement
  from the broader activation transaction and records the temporary requirement
  to serialize candidate staging and approval while
  [#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73) remains open.

## [1.4.0] - 2026-08-08

### Added

- Deterministic active-to-candidate voice evolution deltas with provenance,
  confidence, baseline version and hash evidence, and evidence-backed change
  sets for deliberate rule changes.
- Semantic `voice diff` categories and a separate active-guidance regression
  evaluation for evolved candidates.

### Changed

- Rebuilding an active voice now preserves approved profile prose, constraints,
  rubric, and rules by default. Full regeneration is an explicit replacement
  mode and still requires review and approval.

### Migration

- No stored-data migration is required. Existing manifests remain readable
  because the evolution fields are optional. Routine active-voice rebuilds now
  use the safe evolution path; use `--full-regenerate` only when intentionally
  replacing approved guidance.

## [1.3.0] - 2026-08-08

### Added

- Privacy-safe, repository-tracked publication receipts and the deterministic
  offline `content-creator verify-publications` command.
- Advisory, prospective, and complete receipt-enforcement policies, including
  a hashed legacy-publication baseline for deliberate migration.
- A bounded Perspective Evaluator that records review-required and
  informational semantic findings separately from deterministic failures.
- Exact-draft author resolution for review-required findings, with private
  decision evidence kept under the ignored run and only hashes and finding
  codes copied into tracked receipts.

### Changed

- Repository publication now revalidates exact-draft provenance and pinned
  voice and perspective integrity before writing to a pack destination.
- Possible omitted qualifications, counterpositions, and ambiguous attribution
  now pause selected-perspective publication for author review; informational
  new-position findings do not block publication.

### Migration

- Existing workspaces remain in advisory receipt mode when the policy is absent.
  Generate and inspect a baseline before enabling prospective or complete
  enforcement, then scaffold the new `perspective-evaluator` agent resource.
- Semantic perspective review defaults to `selected-perspectives`. Workspaces
  may explicitly set `semantic_review: off`, but doing so records the opt-out in
  each new publication receipt.

## [1.2.0] - 2026-08-08

### Added

- A supported `content-creator learn <run-id> --feedback ...` operation for
  explicit voice learning from reviewed or already-published runs without
  writing to a content-pack destination.
- Retry-safe learning requests with hashed idempotency keys, input
  fingerprints, verified voice and pack provenance, versioned assessment and
  extraction artifacts, and visible run events.

### Changed

- Publication and learning-only updates now use the same extraction and
  voice-memory application path, retaining existing deduplication, conflict
  detection, and explicit-versus-inferred activation rules.

### Security

- The locked `pypdf` resolution is updated to `6.15.0`, resolving
  `CVE-2026-71852` and `CVE-2026-71870` before release.

### Migration

- No persisted-data migration is required. Learning-only updates require the
  run's exact voice version to remain active and verifiable; placeholder,
  missing, inactive, or tampered voices fail before memory is changed.
- Retry-capable hosts should supply one stable `--idempotency-key` for the same
  run and feedback, and use a new key for intentional additional feedback.

## [1.1.0] - 2026-08-06

### Added

- Resumable in-place revisions for reviewed runs, including author feedback,
  baseline preservation, unified diffs, refreshed validation, criticism,
  quality scores, provenance, and idempotent retry handling.
- Chat-first workspace upgrade compatibility audits that separately report
  dependency state, workspace readiness, and historical-run compatibility.
- Persisted upgrade reports, per-run migration artifacts and events, and an
  approval-gated route for adopting current pack policy and revalidating the
  final draft.
- Configurable inline-link or numbered-reference citation presentation for
  research-backed output.

### Changed

- Redundant legacy pack overrides are migrated automatically when their value
  is identical to the current pack default; differing values remain explicit
  conflicts requiring an author decision.
- Invalid supplied-research input now explains the required JSON contract and
  makes clear that Markdown is unsupported.

### Migration

- Existing workspaces should upgrade their exact dependency pin and lockfile
  to `content-creator==1.1.0`, then review the compatibility audit produced by
  `workspace upgrade --to v1.1.0 --apply`. Compatible historical overrides are
  handled automatically; conflicting runs remain blocked until the author
  explicitly accepts current pack policy.

## [1.0.0] - 2026-08-06

### Added

- Comprehensive Google Style contracts for every production module, class,
  function, and method, including typed arguments, literal defaults, returns,
  explicit exceptions, and contextual descriptions for complex callables.
- Dependency-free structural documentation validation, compatible Ruff
  pydocstyle enforcement, and ADR 0013.
- Blocking Ruff checks for unused arguments and silent `pass` or `continue`
  exception handlers, plus an architecture rule rejecting deleted parameters.

### Changed

- Architecture and readability limits now measure implementation lines while
  continuing to report physical size, so documentation does not consume the
  executable-code budget.
- Recoverable corrupt-record and diagnostic-persistence failures now emit
  bounded warnings, and failed summary writes no longer expose nonexistent paths.

### Stability

- Version 1 establishes the supported CLI, public Python exports, persisted
  schemas, generated-workspace structure, provider interfaces, and approval
  boundaries documented in the Core public-contract and schema policies.
- Future incompatible changes to these supported contracts require a new major
  release and an explicit migration path.

### Migration

- No persisted-data migration is required. Downstream workspaces should upgrade
  their exact dependency pin and lockfile to `content-creator==1.0.0`, then run
  doctor, voice verification, and their workspace tests.

## [0.16.0] - 2026-08-02

### Added

- Blocking readability checks across source, maintenance scripts, and tests:
  500 lines per module, 80 per function, and 7 parameters.
- Ruff hard limits of 15 cyclomatic complexity, 12 branches, 50 statements,
  7 parameters, and 4 nested blocks, with documented lower creation ideals.
- ADR 0011 and consolidated naming, comment, dispatch, and extraction guidance.

### Changed

- Command routing now uses small family handlers and dictionary dispatch.
- Orchestration, workspace creation, voice building and activation,
  perspectives, visual validation, and statistical voice training are split
  into cohesive services behind stable public façades.
- Developer entry points now signpost both module and function-level guardrails.

### Migration

- No persisted-data migration is required. Downstream workspaces should upgrade
  their exact dependency pin to `content-creator==0.16.0`.

## [0.15.0] - 2026-08-02

### Added

- Blocking architecture checks that cap every production module at 500 lines and
  keep the command runtime façade at or below 300 lines.
- A single architecture-guardrail guide and ADR 0010, signposted from every
  Core developer entry point.

### Changed

- The CLI runtime is decomposed into parser composition, general dispatch,
  shared rendering, and independently registered voice and perspective families.
- Orchestration, diagnostics, workspace scaffolding, coordination, voice building,
  voice ML, visual, voice, and perspective code is split by responsibility behind
  compatibility façades; public Python, CLI, schema, and persisted contracts are unchanged.

### Migration

- No workspace or persisted-data migration is required. Downstream workspaces
  should deliberately upgrade their exact dependency pin to `content-creator==0.15.0`.

## [0.14.0] - 2026-08-02

### Added

- A versioned schema catalogue and deterministic `schema list` / `schema export`
  commands for work orders, run states, and voice, perspective, and visual manifests.
- Privacy-safe `operations support-bundle` and `operations recovery-report`
  commands with stable failure codes, lock-owner inspection, and corrupt-state advice.
- Schema evolution, deprecation, operational recovery, and future-development guidance.

### Changed

- Mypy now checks every production module and rejects untyped function definitions.
- Provider and visual CLI families now own their parsing and execution beside the
  existing voice, perspective, schema, and operations command modules.
- Activation locks now record process and creation metadata for safe recovery inspection.

### Migration

- Existing unversioned work orders and run states remain readable as `legacy`
  artifacts and migrate in memory to schema `1.0`. No workspace action is required.

## [0.13.0] - 2026-08-02

### Added

- A stable, small `content_creator.cli` façade with command-family modules
  behind the existing console entry point.
- Explicit research and draft-review stage contracts, plus a narrow optional
  capability seam for visual workflows and statistical voice scoring.
- Shared, tested mechanics for immutable artifact version allocation,
  component hash verification, and exclusive activation locks.
- Enforced architecture rules in CI, expanded Mypy coverage for new boundary
  modules, public-contract characterization tests, ADR 0007, and developer
  principles for future work.

### Changed

- Voice and perspective lifecycles now reuse the same filesystem mechanics
  while retaining their independent domain validation, status, receipt, and
  registry policies.
- Core orchestration no longer directly imports visual or statistical-scoring
  implementations; it composes them through `RunCapabilities`.

### Migration

- No workspace, CLI, schema, or persisted-artifact migration is required.
  Existing integrations and exact package pins continue to work after a
  deliberate upgrade to `0.13.0`.

## [0.12.1] - 2026-08-02

### Fixed

- Visual asset manifest records now embed resolved source provenance, reuse
  rights, and accessibility alt text rather than retaining only source IDs.

## [0.12.0] - 2026-08-02

### Added

- Provider-independent visual contracts for briefs, deterministic and
  generative adapters, source rights, rendered output evidence, asset lineage,
  validation diagnostics, critique, selection, author approval, and manifests.
- Pack-owned visual profiles for supported execution classes, aspect ratios,
  formats, size limits, safe areas, crop simulations, accessibility policy,
  and repository publication destinations.
- A durable `runs/<run-id>/visuals/` lifecycle and `visual` CLI commands for
  creating briefs, validating, critiquing, selecting, approving, inspecting,
  and publishing assets.

### Changed

- Repository publication now gates any active visual manifest on a selected,
  validated, author-approved, hash-matching asset with a known pack consumer.
- The built-in LinkedIn post and article packs support optional 1:1 and 4:5
  visual assets through deterministic or generative adapters. The base
  `general-text` pack remains text-only and fully backward compatible.

### Security

- Exact in-image copy cannot pass without matching OCR or deterministic
  renderer evidence, and source imagery with unresolved reuse rights blocks
  visual validation.

### Migration

- Existing packs remain visual-disabled by default. Pack authors opt in with
  a `visuals` profile; no stored text-only run migration is required.

## [0.11.0] - 2026-08-02

### Added

- Parent-linked revisions now hydrate the parent's reviewed draft, run id,
  content-session id, status, and revision number into a structured writer
  revision context with an explicit unaffected-passage preservation rule.
- Learning candidates now use a schema-level role enum limited to the actual
  prompt consumers: `researcher`, `writer`, and `critic`.

### Changed

- Newly generated workspace READMEs now identify both the immutable Core
  revision and exact package dependency in a small generator-owned section.
- `workspace upgrade --apply` refreshes that managed README section
  transactionally while preserving all repository-authored README content.
  Custom and legacy READMEs without the marker remain untouched.
- Core engineering standards now define formatting, linting, typing, supported
  Python versions, tests, coverage, dependency hygiene, security scanning,
  protected branches, and release expectations.
- Offline CI now tests every declared Python minor version from 3.11 through
  3.14, enforces Ruff formatting, an initial Mypy baseline, 88% statement
  coverage, deterministic evaluation, dependency review, and
  installed-environment vulnerability auditing.
- CodeQL, weekly Dependabot updates, and a private vulnerability reporting
  policy provide code, dependency, secret, and disclosure controls alongside
  the existing release validation.
- Core rejects parent-linked revisions whose parent has no reviewed final draft.
- Unsupported active roles in legacy learning memory now stop prompt assembly
  with a record-specific remediation instead of remaining silently inert.

### Security

- The development test baseline now requires `pytest>=9.0.3`, resolving
  `PYSEC-2026-1845`; CI audits the installed dependency environment so known
  vulnerable resolutions fail before merge.

### Migration

- Core 0.11.0 requires Python 3.11 or newer. Python 3.9 is
  end-of-life, while Python 3.10 reaches end-of-life shortly; workspaces on
  either version must upgrade Python before adopting this release.
- Legacy learning records with unsupported roles may remain provisional or
  rejected. Before upgrading, map each unsupported active record deliberately
  to `researcher`, `writer`, or `critic`, or mark it provisional/rejected for
  author review.

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
