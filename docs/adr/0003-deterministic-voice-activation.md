# ADR 0003: Deterministic voice activation

Status: accepted.

Creative agents may propose and criticise a candidate but cannot activate it.
Activation verifies authorisation, evaluation and hashes; acquires a per-voice
lock; writes an immutable version and approval receipt; and atomically updates
the registry. Repeating an already successful approval is a no-op.
