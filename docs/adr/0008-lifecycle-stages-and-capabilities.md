# ADR 0008: Lifecycle stages and optional capabilities

Status: accepted.

## Context

The orchestrator had accumulated direct knowledge of research, revision,
visual publication, and statistical voice scoring. Voice and perspective
activation also independently implemented the same version allocation, lock,
and component-verification mechanics. Those couplings made unrelated changes
touch the central workflow and allowed filesystem rules to drift.

## Decision

The orchestrator composes explicit research and draft-review stages through
the contracts in `stages.py`. Optional run enrichment is composed through
`RunCapabilities`; the default implementation owns visual workflows and
statistical voice assessment. Optional results remain advisory and cannot
weaken author approval or deterministic publication gates.

Immutable voice and perspective artifacts share only their filesystem
mechanics through `versioned_artifacts.py`: content hashing, component
verification, major-version allocation, and exclusive activation locks. Each
domain retains its own validation, statuses, manifests, receipts, registry
shape, and error language.

The package remains a modular monolith. These seams support tests and current
substitution needs; they are not a general plugin system and are not exported
as stable root-package APIs.

## Consequences

- Research or review-stage tests can substitute one lifecycle responsibility.
- Adding an optional run capability does not require direct orchestrator
  imports of its implementation.
- Hash and activation mechanics have one authoritative implementation.
- Domain-specific voice and perspective policy remains explicit.
- Architecture checks prevent the accepted dependency directions regressing.
