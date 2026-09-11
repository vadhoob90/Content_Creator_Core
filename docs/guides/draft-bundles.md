# Draft bundles and review export

Use a draft bundle to collect independently generated drafts, such as an article
and its LinkedIn hook, for review. Each member keeps its own run, revision,
content session, voice, pack, and approval state. Bundling does not create a
revision relationship between those runs.

```bash
content-creator bundle create launch --title "Launch review"
content-creator bundle add launch article <article-run-id>
content-creator bundle add launch hook <hook-run-id>
content-creator bundle show launch
content-creator bundle review launch
```

Member names are portable lowercase slugs and become Markdown filenames. A run
artifact can occur only once in a bundle. Bundles are stored at
`draft-bundles/<bundle-id>.json`; membership and its order are explicit.

A member pins the exact final text, revision, selected visual, and available
review evidence. An adopted edit, new revision, changed review, or changed visual
selection makes the member stale. Review reports stale members individually;
export requires an explicit update. Unadopted text or media with changed hashes
must first be repaired through the originating workflow.

```bash
content-creator bundle update launch article
content-creator bundle update launch hook --run-id <replacement-hook-run-id>
content-creator bundle remove launch hook
```

An update keeps the member's position. Identical membership operations are
idempotent. Bundles invoke no models and do not change source run artifacts,
approvals, publication receipts, or learning memory.

## Export for review

```bash
content-creator bundle export launch drafts/launch-v1 --preview
content-creator bundle export launch drafts/launch-v1
content-creator export-draft <run-id> content/linkedin-article/drafts/review-v1
```

Preview validates sources, references, destination, and existing output, and
returns the planned manifest without writing files. Destinations must be below
`drafts/` or `content/<pack>/drafts/`, must stay inside the workspace, and must not
traverse symlinks or overlap configured/member publication destinations.

Bundle output contains `<member>.md`, selected visual files under `assets/`, and
`package-manifest.json`. Single-run output uses `content.md`. The manifest records
source and exported hashes, each run's independent lineage and review state,
visual dimensions, format, alt text, asset revision, and provenance references.
Research, prompts, and private review evidence are referenced by hash and path;
their contents are not copied into the package.

Draft exports may contain text with pending claim review and selected visuals
with pending author approval. The manifest preserves those states. Export does
not approve claims, publish content, or trigger learning. Review the package
before sharing it. Editing an exported copy does not adopt those edits into Core;
use `adopt-edit` with that file if you want to make it the run's current draft.

Supported Markdown includes simple inline links/images, one-line reference
link definitions, full/collapsed image references, and shortcut image references.
Local targets must refer to a bundle member's canonical final artifact or its
selected governed media. For example, `../<hook-run-id>/final.md#intro` becomes
`hook.md#intro`. Links with spaces may use angle brackets or URL encoding.
Selected visual alt text replaces the image label. Fenced, indented, and inline
code examples remain unchanged. External HTTP(S), mailto, and fragment links
remain unchanged and are not downloaded. HTML media/link tags, unresolved local
references, and unsupported inline link syntax fail before export; simplify
those references in the source and adopt the edit before retrying.

Exports include every explicit selected [visual slot](visual-slots.md), or the
legacy singleton selection. Exact insertion anchors are applied once; missing or
ambiguous anchors fail before export. Additional approved candidates are not
inferred to be selected placements. Slot identity and review evidence appear in
the package manifest. Coordinator context also exposes bundle review summaries.

## Retries and recovery

The same pinned bundle produces deterministic bytes. An existing destination is
accepted only when every file, directory, and byte matches the intended package.
Changed, extra, incomplete, or unrelated output is never overwritten; choose a
new destination to export an updated bundle.

Core stages and validates the complete package, then installs files without
overwriting existing paths and writes the manifest last. Only a package with its
complete manifest is successful. Ordinary write failures remove only output
created by that attempt. A process interruption can leave an incomplete package
or staging directory. Preserve any manual work, inspect the partial output, and
choose a new destination; Core does not silently reuse an incomplete export.
A stale lock requires the existing operations recovery procedure to verify that
its owner is no longer running before removal.

Core and new author-workspace ignore rules exclude `draft-bundles/`, `drafts/`,
and `content/*/drafts/`. Existing workspaces can add those entries to their own
`.gitignore` before creating private draft review packages.
