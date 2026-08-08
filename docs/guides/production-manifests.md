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

The table identifies the run, resolved content pack and version, voice and
version, zero or more perspective selections, research route, audience,
provider/model routes, revision, creation time, and current status.

The JSON manifest additionally records:

- content-session and parent-run lineage;
- effective pack options;
- citation presentation;
- each privacy-safe provider/model invocation and phase;
- bounded author-contribution provenance;
- paths and hashes for the final draft, context composition, validation, and
  quality evidence when available; and
- repository-local publication path, hash, and timestamp.

It does not copy prompts, model payloads, research text, author contribution
text, API credentials, or published content.

## Publication behavior

Repository publication always reads `final.md`, not `review.md`. Published
content therefore remains clean by default, while its receipt records the
resolved content pack ID and version alongside the existing voice and
perspective evidence.

## Existing runs

Loading an older run is read-only and does not manufacture retrospective
evidence. The next deliberate state-saving operation backfills a manifest from
the evidence that remains available. Missing historical context-composition
data stays missing rather than being inferred.
