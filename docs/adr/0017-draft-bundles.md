# ADR 0017: Pinned draft bundles and non-publishing export

- Status: Accepted for implementation
- Date: 2026-09-11
- Scope: Draft bundle and export slice of #135

## Context

An article, hook, and governed visuals need joint review without combining their
generation lineage or interpreting review export as publication. Drafts and
review evidence can change after membership is selected.

## Decision

A dedicated `draft_bundles` application package owns ordered, versioned bundle
metadata, source snapshots, Markdown reference mapping, and draft package writes.
CLI handlers parse operations and render application results. Bundle and export
contracts appear in the schema catalogue at version 1.0.

Members pin canonical final text, run revision, independent session/parent
identity, available evidence hashes, and explicit selected visual records.
Review compares the complete pin to the current source. An explicit update is
required before exporting stale membership; approval never transfers between
members. Text-only runs remain usable, with missing evidence marked unavailable.
Legacy singleton manifests and explicit slot collections are consumed without
guessing additional selected placements.

Export is a provider-free draft operation that allows pending review while
rejecting conflicting provenance and unresolved local dependencies. Deterministic
filenames and source/export hashes make retries reviewable. Destinations are
confined to workspace draft areas and excluded from configured and member-specific
publication destinations. Source runs, receipts, and learning are unchanged.

Bundle mutations use an exclusive metadata lock. Export additionally takes the
existing author-edit run locks and a destination lock; source pins are checked
again after staging. Files are installed with exclusive hard links from
same-filesystem staging, with the package manifest last as the completion record.
Ordinary failure compensates owned output. Interruption leaves an incomplete
destination requiring inspection. These guarantees do not make a directory
write atomic or require external editors to respect Core locks.

## Consequences

Bundle assembly and export remain independent of generation and publication.
The package contains draft content and selected media, while private research and
review artifacts are referenced rather than copied. Supported Markdown references
are deliberately bounded; unsupported local dependencies require author action
instead of a silently broken package. Exported edits need explicit adoption to
become governed run revisions. Independent visual slots extend selected-media snapshots as specified in ADR
0018. Explicit insertion anchors are validated before draft export or publication.
