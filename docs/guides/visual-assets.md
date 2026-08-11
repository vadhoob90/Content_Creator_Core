# Governed visual workflows

Content Creator can preserve visual work beside a reviewed post or article
without depending on a particular image provider. Core owns the lifecycle and
audit contracts. A content pack owns platform requirements. The downstream
workspace owns author-specific visual voice.

## Natural-language route

Once a post or article run is reviewable, an author can say:

> Create an image for this article.

The packaged `content-creator` skill treats this as an explicit visual-workflow
invocation. It resolves current workspace state rather than guessing a run from
chat history, asks for the run when multiple reviewed candidates are ambiguous,
and invokes:

```bash
content-creator --workspace . visual components <run-id> [--role <role>]
content-creator --workspace . visual render <run-id> \
  --request "Create an image for this article." \
  [--role article-cover] [--variants 2]
```

Core persists the routing decision, exact request, run, pack version, pinned
Core version, role, and selected components in
`runs/<run-id>/visuals/invocation.json`. Missing pack support, roles,
components, or adapters fail with an actionable `VisualError`; the host must
not fall back to untracked image creation.

## Reusable components and rendering

`VisualComponentRegistry.from_core()` reads the immutable component manifest
from the installed Core package. It enumerates versioned contracts, layouts,
renderers, validators, and previews, then resolves compatibility by visual
role, execution class, format, and aspect ratio. Component IDs, versions,
kinds, and provenance are copied into the visual manifest and each asset—not
the reusable component source itself.

Core ships `EditorialSvgRenderer`, a production-capable deterministic adapter
that renders accessible SVG concepts without credentials. Hosts can register a
provider-specific generative implementation through `VisualAdapterRegistry`
and use the same lifecycle. The stable high-level Python path is:

```python
from pathlib import Path

from content_creator import VisualRenderRequest, VisualRequestWorkflow
from content_creator.packs import PackRegistry

root = Path(".")
pack = PackRegistry(root).resolve("linkedin-article")
result = VisualRequestWorkflow(root).render(
    profile=pack.visuals,
    request=VisualRenderRequest(
        run_id="<run-id>",
        pack_id=pack.id,
        pack_version=pack.version,
        request="Create an image for this article.",
        role="article-cover",
        variants=2,
    ),
)
```

The optional workspace file `visual-brand.json` can supply `background`,
`foreground`, `accent`, and `font_family` string tokens. Core validates and
records the effective tokens in the brief; author styling remains owned by the
workspace rather than the reusable package.

## Pack-owned roles

Visual support is inherited and extended through content packs. A child pack
can add roles, formats, safe areas, crop profiles, and execution classes
without copying Core resources or accidentally resetting inherited
`visuals.supported` state.

The LinkedIn article pack declares:

| Role | Ratio | Recommended output |
| --- | --- | --- |
| `article-cover` | 16:9 | 1920 × 1080 |
| `link-preview` | 1.91:1 | 1200 × 627 |
| `portrait-feed` | 4:5 | 1200 × 1500 |
| `square-feed` | 1:1 | 1200 × 1200 |

The LinkedIn post pack defaults to `portrait-feed` and also supports
`square-feed`. Platform requirements remain pack-owned.

## Lifecycle

The workflow is explicit:

```text
reviewed content → visual brief → concept → critique → revision
                 → validation → selection → author approval → publication
```

`VisualBrief` records the connection to the reviewed argument, exact in-image
copy, output ratios and formats, safe-area and crop profiles, hierarchy,
revision invariants, sources and reuse rights, alt text, and optional routing
preferences. Core writes it to `runs/<run-id>/visual_brief.json`.

Adapters implement the `VisualAdapter` contract and declare either
`deterministic` or `generative` execution. They return bytes plus dimensions,
format, content bounding boxes, copy evidence, and provider or renderer
metadata. Core writes concepts and revisions beneath `visuals/` and records
their hashes and parent IDs in `visuals/manifest.json`.

## Validation and approval

Validation checks pack-owned dimensions, ratio, format, file size, safe areas,
crop profiles, alt text, source rights, execution capability, and exact copy.
Exact copy fails closed when an adapter supplies neither OCR output nor
deterministic copy evidence. A selected asset must pass validation and have a
recorded critique. Only the author-approved selected asset can be copied to the
pack's visual destination.

After rendering, use the existing lifecycle commands:

```bash
content-creator --workspace . visual brief <run-id> visual-brief.json
content-creator --workspace . visual validate <run-id> <asset-id>
content-creator --workspace . visual critique <run-id> <asset-id> critique.json
content-creator --workspace . visual select <run-id> <asset-id>
content-creator --workspace . visual approve <run-id> <asset-id>
content-creator --workspace . publish <run-id>
```

`visual render` validates every named variant but does not critique, select, or
approve it. Those human-governed checkpoints remain separate. A revision uses
`visual render <run-id> --parent-asset-id <asset-id>` so lineage is preserved.

## Ownership boundaries

- Core owns component contracts and discovery, its deterministic renderer,
  lineage, routing contracts, validation, and lifecycle.
- Packs own platform ratios, formats, safe areas, crops, and destinations.
- Workspaces own palette, typography, templates, and learned author choices.
- The author remains the final authority; validation never implies approval.
