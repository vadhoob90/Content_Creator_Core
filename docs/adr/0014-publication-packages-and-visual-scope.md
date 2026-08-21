# ADR 0014: Publication packages and visual personalisation scope

- Status: Accepted
- Date: 2026-08-21

## Context

Core 1.13 introduced governed visual briefs, asset lineage, validation,
critique, selection, approval, and visual publication. The publication receipt
and run-level publication contract still described only the Markdown artifact.
Visual-only publication could therefore copy an approved image without updating
run state or the canonical receipt, and a later failure could leave text visible
without the selected media that the author approved as part of the same
communication.

Publication-time learning also treated extraction failure as an event rather
than a durable pending operation. Coordinator recommendations considered runs
independently rather than resolving the authoritative descendant of a content
session. Visual feedback had no safe scope outside linguistic voice memory.

## Decision

Core treats repository publication as a package whose canonical content and
selected media cross one recoverable application boundary:

- run state and production manifests retain structured published-media records;
- new receipts add an optional `artifacts` collection while preserving the
  stable `artifact_path` and `artifact_hash` text contract;
- package publication stages complete bytes, exposes content and media only
  after preflight, writes the receipt as the commit record, and compensates a
  later failure by removing every newly visible destination;
- visual replacement publishes a new immutable media path, retains superseded
  bytes, archives the predecessor receipt, and hash-links the next receipt
  revision without rewriting canonical text;
- exact workspace brand assets are path-confined, hash-pinned, and embedded
  byte-for-byte by deterministic rendering rather than regenerated;
- visual preferences persist under a dedicated `visual-learnings` scope and are
  consumed only by visual briefing;
- publication learning persists a request before provider work and exposes
  idempotent retry through coordinator state; and
- coordinator and verification projections accept bounded lineage and
  publication scopes without weakening repository-wide CI.

Filesystem operations across different destination directories cannot use one
portable operating-system rename. "Atomic publication" therefore means the
observable application guarantee: a failed command compensates all new package
destinations, leaves pre-existing artifacts untouched, and does not report a
published run. The canonical receipt remains the durable commit record.

## Compatibility

All persisted additions are optional under schema version `1.0`. Older run
states read with no published media and no pending learning. Older visual
assets read without a role, locked assets, preferences, or a decision artifact.
Legacy receipts continue to verify their canonical text fields. New writers
emit both those fields and the richer package artifact collection.

Text-only packs and runs remain valid. They publish a package containing only
the canonical content artifact.

## Consequences

Authors can audit the exact text, image, accessibility description, brand
assets, approval, and replacement history as one deliverable. Learning outages
no longer require reconstruction from diagnostics or chat history, and
published descendants no longer leave stale ancestors as coordinator prompts.

The compensating transaction, receipt revision archive, and separate visual
memory add implementation and test surface. Core accepts that cost to keep
visual intent inside the same provenance and recovery guarantees as prose.
