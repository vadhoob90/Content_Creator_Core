# Hotspot cohesion review

This record begins issue #94 with a reproducible current-state baseline. Counts
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
