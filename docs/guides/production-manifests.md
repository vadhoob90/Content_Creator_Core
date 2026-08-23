# Production manifests and review copies

Every newly created content run carries a generated production manifest. Core
builds it from persisted run state; the writer model never writes or edits the
metadata.

## Run artifacts

After run creation, inspect:

| Artifact | Purpose |
|---|---|
| `runs/<run-id>/production-manifest.json` | Versioned, machine-readable production provenance |
| `runs/<run-id>/production-manifest.md` | Compact human-readable production table |
| `runs/<run-id>/review.md` | Production table followed by the reviewed content |
| `runs/<run-id>/final.md` | Clean reviewed content used at publication |

`review.md` appears once the run has a reviewed `final.md`. The production
manifest and table are available earlier and refresh whenever Core saves a run
state, including research checkpoints, failures, revisions, and publication.

The table identifies the run, generation-time Core version, resolved content
pack and version, governed voice artifact and learning epoch, zero or more
perspective selections, research route, audience, provider/model routes,
revision, creation time, and current status. Digests are shortened only in the
human table; the JSON retains each complete digest.

The JSON manifest additionally records:

- content-session and parent-run lineage;
- the exact Core version captured at generation time;
- voice source kind, immutable version, manifest or candidate digest, aggregate
  and version lifecycle status at generation, evidence-baseline digest when
  available, and the exact learning epoch ID, status, and digest;
- every selected perspective ID, immutable version, manifest digest, and
  lifecycle status at generation;
- a canonical `governance_hash` over those stable Core, voice, epoch, and
  perspective fields;
- the immediate predecessor manifest hash when the run revision changes;
- effective pack options;
- citation presentation;
- each privacy-safe provider/model invocation and phase;
- bounded author-contribution provenance;
- paths and hashes for the final draft, context composition, validation, and
  quality evidence when available; and
- repository-local publication path, hash, and timestamp; and
- every selected published visual's role, source and published paths, SHA-256
  hash, MIME type, dimensions, alt text, approval state, and derivation lineage.

It does not copy prompts, model payloads, raw voice evidence, evidence-baseline
contents, private learning text, research text, author contribution text, API
credentials, or published content.

## Snapshot semantics

Governed provenance comes only from the run's persisted
`resolved-context.json`. Core does not re-resolve the live voice registry when
refreshing a production manifest. A later voice upgrade, epoch transition,
deactivation, retirement, or restoration therefore cannot rewrite the state
that generated an older draft.

`source_kind` distinguishes an `approved-version`, an explicit
`candidate-preview`, a `legacy-placeholder`, and other `legacy` evidence. Core
stores a single `artifact_digest` for the selected kind instead of ambiguous
manifest and candidate fields.

## Publication behavior

Repository publication always reads `final.md`, not `review.md`. Published
content therefore remains clean by default, while its receipt records the
resolved content pack ID and version alongside the existing voice and
perspective evidence. Package-aware receipts enumerate the canonical text and
all selected media; text-only runs continue to publish without media entries.
New receipts also record the run-local production-manifest path and stable
governance hash. Verification recomputes that hash from the manifest, so status,
publication timestamps, and media updates can refresh without breaking the
generation-time binding.

## Existing runs

Loading an older run is read-only and does not manufacture retrospective
evidence. The next deliberate state-saving operation backfills a manifest from
the evidence that remains available. Missing historical context-composition
data stays missing rather than being inferred. A missing generation-time Core
version, voice version, artifact digest, learning epoch, or perspective digest
is represented by `null` plus an explicit `unavailable` or `partial` provenance
status and reason. Core never stamps its current installed version onto a
historical run.
