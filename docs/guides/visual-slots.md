# Multiple visual slots

A visual slot names one placement within a reviewed article. Each slot owns an
editorial purpose, role, display order or insertion anchor, exact text revision,
brief revision, selection, and approval. Changing one slot leaves all other
selections and approvals intact.

Finish author edits before defining slots. When the final text changes, its
slots become stale: explicitly refresh each affected slot brief, create or import
its candidate, and review it again. Claim approval alone does not change the text
revision or invalidate visual approval.

## Define a placement

Save a typed brief, for example `interaction-brief.json`:

```json
{
  "run_id": "ARTICLE_RUN_ID",
  "slot_id": "interaction",
  "role": "article-inline-diagram",
  "display_order": 1,
  "insertion_anchor": "<!-- visual:interaction -->",
  "objective": "Explain how the author, writer, and critic interact",
  "content_connection": "Illustrates the article's reviewed workflow description",
  "platform_profile": "linkedin-article:article-inline-diagram",
  "aspect_ratios": ["16:9"],
  "output_formats": ["svg", "png"],
  "output_width": 1920,
  "output_height": 1080,
  "revision_invariants": ["Keep human approval distinct from model feedback"],
  "alt_text": "The author directs the writer and reviews feedback from the critic."
}
```

Use the actual run ID. Put `<!-- visual:interaction -->` exactly once in the
source Markdown and adopt that edit before defining the slot:

```bash
content-creator visual brief ARTICLE_RUN_ID interaction-brief.json
```

Repeating `brief` for the same slot creates a new immutable brief revision and
clears only that slot's selection and approval. Previous candidates and reviews
remain in the manifest and `visuals/slots/<slot-id>/rNNNN/` history. After an
interrupted brief write, inspect any unreferenced revision before retrying; Core
will not overwrite that revision silently. Run locks use the existing operations
recovery procedure to check whether the recorded process is still active.

The article pack supports `article-cover`, `article-inline-diagram`, `comparison`,
and `facts-panel`, plus its existing feed roles. The bundled deterministic
renderer supports its existing headline-card roles. Diagram, comparison, and
facts-panel roles require a compatible host adapter or governed image import;
Core does not relabel a headline card as a diagram.

For a supported renderer and existing slot brief:

```bash
content-creator visual render ARTICLE_RUN_ID --slot cover
content-creator visual render ARTICLE_RUN_ID --slot cover --parent-asset-id PREVIOUS_ASSET_ID
```

A render reads the pinned brief. Change objective or alt text through a new brief
revision instead of a render override. Candidate revisions must remain in the
same slot. Each render invocation, candidate validation, critique, and decision
has its own slot/revision location; candidates from older brief revisions cannot
receive approval under the new brief.

## Import and review an existing image

Save `interaction-import.json` with the exact source provenance known to you:

```json
{
  "run_id": "ARTICLE_RUN_ID",
  "slot_id": "interaction",
  "path": "author-assets/interaction.svg",
  "source": {
    "uri": "author-assets/interaction.svg",
    "creator": "Author",
    "rights_status": "owned"
  }
}
```

```bash
content-creator visual import ARTICLE_RUN_ID interaction-import.json
content-creator visual critique ARTICLE_RUN_ID ASSET_ID critique.json
content-creator visual select ARTICLE_RUN_ID ASSET_ID
content-creator visual approve ARTICLE_RUN_ID ASSET_ID
```

A critique file can contain `{"summary": "Reviewed labels, connections, and alt text"}`.
Import returns the new asset ID and technical diagnostics. It preserves the
original bytes and never selects or approves them. Use `parent_asset_id` in the
import request for a revision of an earlier candidate from the same slot.

Supported imports are self-contained SVG and single-frame PNG, JPEG, or WebP.
Raster bytes are verified and decoded, with a 40-million-pixel limit. SVG must
have explicit width/height and contain no scripts, external resources, or style
blocks. Pack size, format, ratio, copy, and rights checks still apply. If exact
copy is required but no reliable extraction evidence exists, validation reports
that limitation instead of claiming the copy was verified. Unknown rights remain
`unverified` and prevent selection/approval until the author supplies valid source
evidence in a new import. Import does not assert unknown source history.

Approval binds the asset identity and hash, accessibility text, immutable brief,
source provenance, and owning text revision. Technical validation alone does not
establish editorial usefulness. Replacing or editing these inputs cannot retain
an earlier approval silently.

## Review, export, and publication

`visual show` returns every slot and candidate. `coordinator next-actions`
projects per-slot review requirements; coordinator capabilities list the slot and
bundle commands. Production manifests reference the complete visual collection.

[Draft bundles](draft-bundles.md) export every selected placement and its review
state. Missing or duplicate insertion anchors are errors. Without an explicit
anchor, existing supported Markdown links are rewritten and the media is included
in display order; Core does not guess a prose insertion point.

Publication checks approval and source integrity for the complete collection
before writing the text and selected media. Receipts record slot IDs, source and
published paths, hashes, dimensions, alt text, and asset revisions. Source final
Markdown remains unchanged; published Markdown gets resolved relative links.

For a published slot, import or render and approve its replacement, then use:

```bash
content-creator visual replace ARTICLE_RUN_ID NEW_ASSET_ID
```

A slot replacement creates a new immutable Markdown snapshot and receipt linked
to the predecessor. Earlier text, media, and receipts remain intact, and the run
points to the new package. Other slots retain their media and approvals. The
legacy singleton replacement workflow keeps its existing behavior.

## Legacy compatibility

Existing text-only and singleton runs remain supported. To add independently
named slots to a run that already has a global selection:

```bash
content-creator visual migrate-slots ARTICLE_RUN_ID
```

Migration retains the exact original manifest and brief, keeps all candidates,
and maps the verified current selection into a `legacy` slot. Existing current
approval is retained only with matching media bytes, brief alt text, and passing
validation. Unselected historical candidates do not receive invented brief
bindings; create or import a new slot candidate to use them in the new workflow.
Migration is idempotent once complete.

Collections use visual-manifest schema `1.1`; new readers reject slot data marked
as `1.0` or combined with a global selection. Use Core 1.20 or newer to mutate
multi-slot runs. Legacy singleton schema `1.0` remains readable and writable for
runs that have not migrated.
