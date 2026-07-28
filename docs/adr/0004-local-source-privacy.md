# ADR 0004: Local source privacy

Status: accepted.

Complete normalized source text remains in ignored `.voice-cache/`. Versioned
voice packages store provenance metadata, hashes and analysis outputs. This
reduces accidental publication of private corpora while keeping builds
traceable. The repository owner remains responsible for source authorisation
and retention.
