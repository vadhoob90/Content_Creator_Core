# Hotspot cohesion review

This record completes issue #94 with a reproducible before-and-after review. Counts
come from `scripts/readability_report.py`; dependencies come from
`scripts/architecture_report.py --json`. Import count is a navigation signal,
not proof that a module should be split.

## Current decisions

| Hotspot | Implementation lines | Direct production importers | Decision | First durable seam to assess |
| --- | ---: | ---: | --- | --- |
| `voice_evolution` | 500 | 2 | Extract selectively | Pure proposal/change-set and merge-delta policy; retain `VoiceEvolution` as façade. |
| `orchestration_support` | 496 | 1 | Simplify through collaborators | Draft/review loop and research execution policy; do not recreate support inheritance. |
| `voice_ml.training` | 492 | 2 | Extract selectively | Reliability/eligibility policy before classifier or persistence work. |
| `coordinator` | 487 | 3 | Extract selectively | State-to-action and recommendation policy; retain coordinator entry point. |
| `orchestrator` | 479 | 7 | Retain façade, clarify transactions | Start-context and publication transaction boundaries after characterisation. |
| `voice_build.pipeline` | 459 | 1 | Simplify through package collaborators | Source acquisition/cache and artifact preparation; preserve ordering and cleanup. |
| `publication_provenance` | 461 | 3 | Extract selectively | Pure per-domain verification and report aggregation; preserve fail-closed paths. |

## Dependency and responsibility map

### Voice evolution

- Responsibilities: baseline discovery, proposal application, evidence checks,
  deterministic merge/delta calculation, and result persistence.
- Depends downward on storage, versioned artifacts, voice-build models, and
  voice models.
- Used by schema registration and the voice-build pipeline.
- First slice: characterise merge/delta outputs, then move only pure policy with
  no filesystem access. Mutation evidence can be added after the initial
  quality/versioning baseline is understood.

### Orchestration runtime and façade

- `orchestration_support` coordinates configuration, diagnostics, research,
  learning, prompting, publication, quality, revision, validation, and runner
  boundaries; only `orchestrator` imports it.
- `orchestrator` is the supported lifecycle façade used by package exports, CLI,
  commands, and evaluation.
- First slice: map start and publication transactions and characterise persisted
  state transitions before extracting policy. The façade remains stable.

### Voice ML training

- Responsibilities: corpus rows, source signatures, reliability, eligibility,
  classifier execution, preprocessing metadata, and artifacts.
- Depends on ingestion, linguistics, storage, optional dependency isolation, and
  active voice resolution.
- First slice: extract deterministic reliability/eligibility decisions only;
  keep optional imports and model fitting behind their present boundary.

### Coordinator

- Responsibilities: capability snapshot, run/provider/voice status, available
  actions, recommendations, and artifact discovery.
- Depends on configuration, typed coordinator models, health, packs, storage,
  upgrade audit, rejection state, and voices.
- First slice: separate pure state-to-action and recommendation decisions from
  filesystem snapshot readers, with table-driven characterisation tests.

### Voice-build pipeline

- Responsibilities: source collection, attribution, analysis, evaluation,
  rendering, manifest creation, evolution, and candidate publication.
- Depends on the focused `voice_build` package plus ingestion, linguistics,
  runner, storage, versioned artifacts, evolution, and voice contracts.
- First slice: review source acquisition/cache as a lifecycle boundary. Do not
  separate steps whose ordering and cleanup invariants are coupled.

### Publication provenance

- Responsibilities: receipt issuance, baseline discovery, semantic/voice/
  perspective verification, path containment, and reporting.
- Used by runtime commands, orchestration, and publication lifecycle.
- First slice: extract deterministic domain findings only after fixtures cover
  every machine-readable classification and tampered-path outcome.

## Delivery order

1. Coordinator action/recommendation policy.
2. Voice-ML reliability/eligibility policy.
3. Voice-evolution merge/delta policy.
4. Publication domain verification.
5. Voice-build source acquisition/cache.
6. Orchestration transaction clarification.

Each slice must reduce the policies or side effects a reader tracks, preserve
public imports and persisted formats, pass the full gate, and record why any
remaining density is cohesive. Stop when an extraction would add forwarding
layers without an independently testable domain responsibility.

## Implemented slices

Two independent policy seams were extracted without changing the CLI, package
exports, schemas, or persisted artifacts:

- `coordinator_policy` now owns state-to-action routing and workspace
  recommendations. `ContentCoordinator` remains the stable filesystem-facing
  façade and retains its private callable hooks for compatibility with existing
  tests and integrations.
- `voice_ml.reliability` now owns corpus thresholds, balance assessment,
  preflight summaries, and fail/confirmation results. Optional ML imports,
  feature preparation, fitting, evaluation, and artifact persistence remain in
  `voice_ml.training`.

The existing characterisation suites exercise every coordinator recommendation
branch, lifecycle action route, and all three ML reliability outcomes. The
extracted functions have no filesystem, provider, or optional-dependency access.

## Final architecture review

| Hotspot | Before | After | Final decision and dependency rationale |
| --- | ---: | ---: | --- |
| `coordinator` | 487 | 294 | Extract policy. The façade reads workspace state; the new module depends only on coordinator/domain models and does not import the façade. |
| `voice_ml.training` | 492 | 379 | Extract policy. Reliability is independently testable and points inward to no training or optional ML dependency. |
| `voice_evolution` | 500 | 500 | Retain for now. Proposal application, evidence authorization, delta construction, and staged writes form one fail-closed candidate transaction; moving helpers alone would create a stateful forwarding layer. Reassess if a second consumer needs delta policy. |
| `orchestration_support` | 496 | 496 | Retain private runtime collaborator. It has one importer and owns the ordered draft/review/research transaction; splitting by step would expose partially valid lifecycle state. |
| `orchestrator` | 479 | 479 | Retain stable façade. Seven production importers use this lifecycle boundary; its work is delegated already, and another façade would increase navigation without isolating policy. |
| `voice_build.pipeline` | 459 | 459 | Retain package orchestrator. Corpus acquisition (`voice_build.corpus`), models, and rendering are already extracted; remaining ordering, cleanup, and candidate assembly are one transaction. |
| `publication_provenance` | 461 | 461 | Retain fail-closed verifier. Domain checks share resolved workspace paths, registries, and one finding/report contract; extraction would either duplicate containment checks or pass a broad mutable context. Reassess when a verifier gains a second caller. |

The two selected modules are now below the 400-line focused-review threshold.
Every remaining hotspot above 400 has an explicit cohesion and dependency-
direction justification, rather than a size-only exemption.

## Transaction boundaries

- Content runs: `orchestrator` is the public boundary;
  `orchestration_support` owns ordered runtime steps and only returns valid
  persisted lifecycle states.
- Voice candidates: `voice_build.pipeline` owns acquisition through isolated
  candidate assembly; `VoiceEvolution` applies evidence and writes its delta
  inside that staging boundary.
- Publication verification: `PublicationProvenance` resolves workspace-local
  evidence and aggregates one deterministic report; callers never perform a
  partial domain verification as a substitute for the complete check.
