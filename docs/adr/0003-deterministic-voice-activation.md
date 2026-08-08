# ADR 0003: Deterministic voice activation

Status: accepted.

Creative agents may propose and criticise a candidate but cannot activate it.
Activation verifies authorisation, evaluation and hashes; acquires a per-voice
lock; writes an immutable version and approval receipt; and atomically updates
the registry. Repeating an already successful approval is a no-op.

## Implementation status

The registry file is replaced atomically and concurrent approvals share an
exclusive lock. Candidate build/replacement does not yet share that lock, and
the version directory, receipt, and registry are not committed as one
transaction. Operators must serialize build and approval until snapshot-safe,
transactional promotion in
[#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73) is complete.
This is an implementation gap against the decision, not a change to the
approval boundary.
