# Visual asset workflows

Content Creator can preserve visual work beside a reviewed post or article
without depending on a particular image provider. Core owns the lifecycle and
audit contracts. A content pack owns platform requirements. The downstream
workspace owns author-specific visual voice.

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

Useful commands for externally rendered assets are:

```bash
content-creator --workspace . visual brief <run-id> visual-brief.json
content-creator --workspace . visual validate <run-id> <asset-id>
content-creator --workspace . visual critique <run-id> <asset-id> critique.json
content-creator --workspace . visual select <run-id> <asset-id>
content-creator --workspace . visual approve <run-id> <asset-id>
content-creator --workspace . publish <run-id>
```

Rendering hosts register adapters through the Python API and call
`VisualWorkflow.execute`. The CLI deliberately does not encode provider names
or credentials.

## Ownership boundaries

- Core owns schemas, lineage, routing contracts, validation, and lifecycle.
- Packs own platform ratios, formats, safe areas, crops, and destinations.
- Workspaces own palette, typography, templates, and learned author choices.
- The author remains the final authority; validation never implies approval.
