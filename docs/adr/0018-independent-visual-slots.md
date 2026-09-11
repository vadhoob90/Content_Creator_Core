# ADR 0018: Independent visual placements and collection publication

- Status: Accepted
- Date: 2026-09-11
- Scope: Complete the visual-placement and bundle integration work in #135

## Decision

Add explicit slots to visual-manifest schema 1.1 while continuing to read legacy
singleton schema 1.0. Each placement binds exact owning text bytes/revision, an
immutable brief revision, a selected candidate, and approval over media, alt text,
source provenance, and placement context. Named placements never share a global
selection. Existing unselected candidates remain historical evidence.

Keep deterministic technical validation in a composed validator, visual mutation
locking in a dedicated boundary, and collection publication separate from the
legacy singleton compatibility path. Nested visual operations share the author
edit/publication run lock. Current visual projections update existing production
metadata without reconstructing historical voice, pack, or context inputs.

Register host-created images through a typed import operation. Preserve original
bytes and declared provenance, decode supported raster formats with Pillow, and
validate supported self-contained SVG. Unknown rights remain explicit blockers.
Pack roles describe the editorial job; renderer compatibility remains explicit.
No diagram capability is inferred from the existing headline-card renderer.

Bundle exports and publication apply exact insertion anchors and package every
selected placement. Publication requires all current approvals. A slot media
replacement creates a new immutable Markdown snapshot and linked receipt while
retaining prior publications and every unaffected media item. This preserves
published artifacts without leaving current inline links pointed at replaced
media. Failed package writes compensate only destinations owned by that attempt.

## Compatibility

Explicit migration preserves the original manifest/brief verbatim and binds the
verified selected legacy candidate to one legacy slot. The new writer rejects
slot collections labelled as singleton schema or carrying a global selection.
Old Core binaries must not mutate schema 1.1 collections. Receipt/media slot IDs
and production slot projections are additive fields; existing text-only and
singleton publication behavior remains supported.
