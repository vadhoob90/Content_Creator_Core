# Schemas and commands

The examples show logical contracts. Implementation uses versioned Pydantic
models and emitted JSON Schema.

## Voice work order

```json
{
  "person": {
    "display_name": "Aisha Khan",
    "voice_id": "aisha-khan"
  },
  "authorisation": {
    "confirmed": true,
    "attested_by": "Bharath",
    "intended_uses": ["linkedin-post", "linkedin-article"],
    "expires_at": null,
    "revoked_at": null
  },
  "sources": {
    "urls": ["https://example.com/article"],
    "documents": ["voice-material/aisha/speech.docx"]
  },
  "representative_sources": [],
  "excluded_sources": [],
  "target_audiences": ["technology leaders"]
}
```

## Source record

```json
{
  "id": "source-001",
  "kind": "webpage",
  "locator": "https://example.com/article",
  "content_hash": "sha256:...",
  "title": "Article title",
  "publication_date": "2026-04-12",
  "usage_basis": "authorised_voice_analysis",
  "retention": "metadata_and_hash_only",
  "attribution": {
    "classification": "directly_authored",
    "confidence": 0.98,
    "voice_weight": "high",
    "evidence": ["Visible byline and structured metadata agree"],
    "needs_human_review": false
  },
  "cache_path": ".voice-cache/aisha-khan/source-001.json",
  "approved_for_analysis": true
}
```

## Profile manifest

```yaml
schema_version: "1.0"
id: aisha-khan
display_name: Aisha Khan
version: 1.0.0-candidate
status: awaiting_approval

components:
  profile: profile.md
  constraints: constraints.yaml
  rubric: voice-rubric.yaml
  learnings: learnings.json
  sources: source-index.json
  evaluations: evaluation-cases.yaml
  evaluation_report: evaluation-report.json

supported_packs:
  linkedin-post: medium
  linkedin-article: high

authorisation:
  confirmed: true
  intended_uses: [linkedin-post, linkedin-article]
  expires_at: null
  revoked_at: null
```

## Voice pattern

```json
{
  "id": "pattern-012",
  "name": "Concrete operational opening",
  "description": "Often opens technical explanations with a recognisable operational problem.",
  "scope": ["long-form-technology"],
  "status": "confirmed",
  "confidence": 0.91,
  "supporting_source_ids": ["source-002", "source-005", "source-011"],
  "counterexample_source_ids": ["source-008"],
  "mandatory": false
}
```

## Voice rubric

```yaml
dimensions:
  characteristic_alignment:
    minimum: 8
  naturalness:
    minimum: 8
  personal_integrity:
    minimum: 10
  channel_fit:
    minimum: 8
  non_imitation:
    minimum: 10

hard_gates:
  invented_personal_context_allowed: false
  unsupported_biographical_claims_allowed: false
  material_phrase_overlap_allowed: false
```

## Approval receipt

```json
{
  "voice_id": "aisha-khan",
  "candidate_version": "1.0.0-candidate",
  "activated_version": "1.0.0",
  "approved_by": "bharath",
  "approved_at": "2026-08-10T14:35:00Z",
  "authorisation_hash": "sha256:...",
  "profile_hash": "sha256:...",
  "rubric_hash": "sha256:...",
  "evaluation_report_hash": "sha256:...",
  "evaluation_score": 8.6,
  "override": null
}
```

## Content brief

```json
{
  "request": "Explain engineering career progression",
  "voice_id": "aisha-khan",
  "content_pack": "linkedin-post",
  "objective": "explain",
  "audience": "technology leaders",
  "research": {
    "depth": "none",
    "source": "none"
  },
  "constraints": []
}
```

## Resolved run context

```json
{
  "engine_version": "1.0.0",
  "content_pack": {
    "id": "linkedin-post",
    "version": "1.0.0"
  },
  "voice": {
    "id": "aisha-khan",
    "version": "1.0.0"
  },
  "component_hashes": {},
  "active_learning_ids": [],
  "resolved_at": "2026-08-10T15:10:00Z"
}
```

## CLI

### One-time setup

```bash
content-studio init
content-studio provider verify anthropic
```

### Voice creation

By default, `voice create` continues through ingestion, analysis, build and
evaluation, stopping at `awaiting_approval`. `--no-build` supports staged
operation and recovery.

```bash
content-studio voice create \
  --name "Aisha Khan" \
  --authorised-by "Bharath" \
  --use linkedin-post \
  --use linkedin-article \
  --sources source-urls.txt \
  --documents voice-material/aisha/

content-studio voice create \
  --name "Aisha Khan" \
  --sources source-urls.txt \
  --no-build
```

### Build and inspect

```bash
content-studio voice build aisha-khan
content-studio voice status aisha-khan
content-studio voice show aisha-khan
content-studio voice verify aisha-khan
```

### Deterministic approval

```bash
content-studio voice approve aisha-khan
```

Optional explicit editorial override:

```bash
content-studio voice approve aisha-khan \
  --override-evaluation \
  --reason "Approved directly by the profile owner"
```

Authorisation, invalid schema and corrupted provenance are never overridable.

### Voice maintenance

```bash
content-studio voice list
content-studio voice add-sources aisha-khan --sources additional-urls.txt
content-studio voice rebuild aisha-khan
content-studio voice diff aisha-khan --from 1.0.0 --to candidate
content-studio voice deactivate aisha-khan \
  --reason "Authorisation withdrawn"
```

Deactivation prevents future content runs but preserves old manifests,
receipts and run snapshots. Reactivation requires a new explicit approval.

### Content creation

```bash
content-studio content run \
  "Explain engineering career progression" \
  --voice aisha-khan \
  --pack linkedin-post \
  --research none

content-studio content status <run-id>
content-studio content approve <run-id>
content-studio content finalize <run-id>
```

`approve` records author acceptance. `finalize` writes the channel-ready
repository artifact. External distribution is not part of the initial scope.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success, including an idempotent no-op |
| 2 | Invalid command or schema |
| 3 | Human clarification required |
| 4 | Candidate not built or not evaluated |
| 5 | Evaluation gate failed |
| 6 | Authorisation or provenance blocker |
| 7 | Lock conflict |
| 8 | Provider or external-source failure |
