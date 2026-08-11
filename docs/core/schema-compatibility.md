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

The authoritative catalogue lives in `content_creator.schema_registry`.
Pydantic models remain the single source of truth; exported schemas are build
artifacts and must not be edited by hand.
