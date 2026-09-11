# Schema compatibility and evolution

Core treats persisted JSON as a versioned interface. Work orders, run states,
voice manifests, perspective manifests, and visual manifests write
`schema_version: "1.0"` and publish deterministic JSON Schemas. Publication
receipts and prospective-enforcement baselines use the same governed schema
catalogue. Voice evolution change sets and deterministic semantic deltas are
also published through that catalogue.

Inspect the catalogue or export a reviewable bundle offline:

```bash
content-creator schema list
content-creator schema export build/schemas
```

`index.json` records the current writer version, supported reader versions,
and stable filenames. Schema files include stable `$id` values.

## Compatibility policy

- Writers emit only the current canonical version.
- Readers accept the current version and explicitly listed older versions.
- Unversioned artifacts are the `legacy` read version and migrate in memory to
  `1.0`; the source mapping is never mutated.
- Unknown versions fail with `SchemaCompatibilityError` instead of being
  guessed.
- A migration requires a historical fixture and a test proving the old form
  can be read without data loss.
- Deprecation is announced in a minor release and supported for at least one
  subsequent minor release. Removal requires a major release with a migration
  command and release note.

Adding an optional field is normally backward compatible. Removing or
renaming a field, changing its meaning, narrowing valid values, or changing a
default requires a migration and explicit compatibility review.

Visual manifests written from Core 1.13 add optional component references and
variant names while retaining schema version `1.0`. Older manifests read with
empty component lists and unnamed assets; their next explicit visual render can
backfill current installed-component references without changing prior assets.

Core 1.15 adds optional publication-package artifacts, receipt revision links,
published-media state, visual roles, locked-asset references, visual
preferences, visual decisions, pending-learning counts, and coordinator lineage
fields while retaining schema version `1.0`. Legacy text-only receipts continue
to verify through `artifact_path` and `artifact_hash`; writers emit the richer
artifact collection for new publications without mutating historical receipts.

Core 1.18 additively extends schema `1.0` production manifests with nullable
generation-time Core identity, governed voice and learning-epoch state,
perspective manifest digests, governance hashes, revision lineage, and
publication-receipt references. Publication receipts add optional production
manifest and governance-hash bindings. Older manifests and receipts remain
readable; absent provenance stays explicitly unavailable instead of being
reconstructed from current registry state.

The authoritative catalogue lives in `content_creator.schema_registry`.
Pydantic models remain the single source of truth; exported schemas are build
artifacts and must not be edited by hand.

## Author-edit integrity additions

The author-edit slice of #135 adds optional `claim_review_required` state and
coordinator fields, optional `draft_integrity` production metadata, and version
1.0 `draft-integrity` / `edit-claim-review` schemas. New resolved contexts also
capture `effective_pack` and `effective_pack_sha256`. Historical contexts remain
readable; missing effective inputs remain unavailable for adoption unless a
matching standalone pack can be verified. Accepted snapshots and recovery
journals live within ignored run directories. Existing text writers and legacy
receipt shapes are unchanged. See [author edits](../guides/author-edits.md).

## Draft bundle additions

Issue #135 adds version 1.0 `draft-bundle`, `draft-bundle-review`, and
`draft-export-manifest` schemas. Bundle metadata pins independent run identities,
text/evidence hashes, and selected visual records. Unknown bundle schema versions
are rejected. Text-only runs remain supported, with unavailable historical
evidence represented explicitly. Existing singleton visual selections retain
their semantics. No publication receipt schema or source run migration is
required. See [draft bundles](../guides/draft-bundles.md).

## Visual collection schema 1.1

Core 1.20 adds explicit visual slots, per-brief candidate bindings, and exact
approval hashes in visual-manifest schema `1.1`. Legacy singleton `1.0` remains
supported; slot data cannot be written under the legacy version or with a global
selection. Explicit migration preserves historical artifacts and only binds the
verified current selected candidate. Use Core 1.20+ for collection mutations.
The schema catalogue reports per-kind read versions; unrelated schemas remain
at 1.0. Publication media/receipt slot IDs and production slot projections are
additive optional fields. See [visual slots](../guides/visual-slots.md).
