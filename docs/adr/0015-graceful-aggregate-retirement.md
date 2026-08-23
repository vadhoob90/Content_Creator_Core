# ADR 0015: Graceful aggregate retirement

## Decision

Voice and perspective manifests remain immutable content artifacts. Pause,
reactivation, retirement, restoration, exact-hash candidate disposition, and learning
epoch transitions are recorded in separate content-addressed receipts under the
aggregate lifecycle directory. A reconstructed per-version catalogue records selected,
superseded, deactivated-with-voice, retired-with-voice, and historical relationships.

Transitions hold the existing lifecycle lock and use a compensating multi-artifact
transaction for registry, default configuration, learning epoch, run decisions,
receipt, and catalogue writes. Retirement plans bind persisted state by canonical hash.

## Consequences

New work resolves only active aggregates. Historical pinned versions remain readable
and verifiable. Pausing and reactivation do not allocate a content version. Retirement
never implies deletion and does not silently cascade semantic context changes.
