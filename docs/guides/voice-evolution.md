# Safe voice evolution

An active voice is an approved editorial contract. Adding new source material
therefore evolves that contract by default; it does not silently regenerate it.
The active version stays usable until a human approves the new candidate.

## Default workflow

```bash
content-creator voice add-sources <voice-id> --documents "/path/to/new-writing"
content-creator voice rebuild <voice-id>
content-creator voice diff <voice-id>
content-creator voice approve <voice-id> --approved-by "Repository Owner"
```

When an active version exists, `voice rebuild` uses it as an immutable baseline.
The candidate preserves its profile prose, constraints, rubric, and structured
patterns. Newly derived, non-conflicting patterns may be added for review, but an
approved rule is never modified or removed merely because a fresh analysis did
not rediscover it.

`voice diff` compares `active` with `candidate` by default. Its semantic delta
separates `retained`, `added`, `modified`, `superseded`, and `removed` guidance.
Review this output before approval.

## Evolution evidence

Every evolved candidate contains:

| Artifact or field | Purpose |
|---|---|
| `voice-evolution.json` | Deterministic semantic delta, provenance, confidence, and rationale |
| `evaluation-report.json` → `regression_evaluation` | Separate check for unexplained loss of approved guidance |
| `manifest.json` → `baseline_version` | Immutable active version used as the baseline |
| `manifest.json` → `baseline_candidate_hash` | Exact approved candidate hash used as the baseline |
| `manifest.json` → `evolution_delta_hash` | Integrity hash for the semantic delta |

A candidate cannot be approved if its baseline has changed or its active
components, manifest, registry entry, or evolution delta fail verification.

## Propose a deliberate rule change

Use a change set when new authorised evidence justifies a semantic change. For
example, this proposal supersedes one approved opening rule:

```json
{
  "schema_version": "1.0",
  "changes": [
    {
      "action": "supersede",
      "target_id": "opening-rule",
      "replacement": {
        "id": "precise-opening-rule",
        "name": "Precise opening",
        "description": "Open with a precise, evidence-backed tension.",
        "status": "for-review",
        "confidence": 0.9,
        "supporting_source_ids": ["source-003"],
        "mandatory": true,
        "category": "openings",
        "generation_guidance": "Open with a precise tension.",
        "anti_pattern": "Do not overstate the opening claim."
      },
      "evidence_source_ids": ["source-003"],
      "confidence": 0.9,
      "rationale": "The new article supports a narrower opening rule."
    }
  ]
}
```

```bash
content-creator voice rebuild <voice-id> --change-set voice-change-set.json
content-creator voice diff <voice-id>
```

Supported actions are `retain`, `add`, `modify`, `supersede`, and `remove`.
Additions require a new replacement pattern. Modifications retain the target ID;
supersessions use a new ID. Changes and removals require authorised source IDs,
confidence, and a rationale. They remain proposals until explicit approval.

## Full replacement

Use full regeneration only when the author explicitly intends to replace the
approved guidance:

```bash
content-creator voice rebuild <voice-id> --full-regenerate
content-creator voice diff <voice-id>
```

Full replacement still records every semantic loss in `voice-evolution.json`,
runs the regression evaluation in explicit-replacement mode, and requires human
approval. It cannot be combined with a change set.

Builds are staged atomically. A failed evolution leaves both the active version
and the previous valid candidate unchanged. This guarantee covers candidate
construction and replacement, not the later multi-file approval transaction.

## Operational concurrency limit

Run `voice rebuild` and `voice approve` serially. Do not start another build or
rebuild for the same voice while approval is in progress. Approval currently
validates the mutable `candidate/` directory before taking its activation lock,
and promotion is written across the version directory, receipt, and registry in
separate steps. Concurrent candidate replacement or an interruption between
those writes can therefore leave mixed or partial lifecycle artifacts.

If approval overlaps a rebuild or is interrupted, stop mutating that voice and
preserve the workspace for inspection. Do not delete a numeric version directory
or edit the registry by hand. Snapshot-safe, transactional promotion is tracked
in [#73](https://github.com/vadhoob90/Content_Creator_Core/issues/73).
