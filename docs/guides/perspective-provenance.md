# Perspective provenance

Perspective provenance records what an author has explicitly said, approved, or
qualified. It is optional and remains separate from linguistic voice and
research.

```text
voice        = how the author communicates
perspective  = what the author believes, recommends, or interprets
research     = what external evidence supports, qualifies, or challenges
brief        = what this particular piece is trying to contribute
```

A perspective entry is never factual authority. Packs may add domain-specific
claim types, but the generic engine never treats an approved opinion as proof.

## Context isolation

Every perspective belongs to one voice identity and one explicit context:

```text
experienced-lawyer
├── legal-training
└── space-law
```

Contexts do not inherit from one another. The orchestrator never selects a
perspective from topic similarity. A run loads a context only when the user or
validated brief names it.

This permits a shared linguistic voice while keeping established legal-training
positions separate from emerging space-law views.

## Create a context

Create an empty context when the author has not approved any reusable position:

```bash
content-creator perspective create \
  --voice experienced-lawyer \
  --context space-law
```

Or create it with a directly supplied entry:

```bash
content-creator perspective create \
  --voice experienced-lawyer \
  --context legal-training \
  --statement "Training should teach recognition and escalation." \
  --type principle \
  --topic training \
  --qualification "Mandatory procedures may still require exact recall." \
  --evidence "Direct author interview, 2026-07-28"
```

An entry requires evidence. The candidate may contain qualifications,
counterpositions, topics, confidence, and provenance.

Inspect and approve:

```bash
content-creator perspective status \
  --voice experienced-lawyer --context legal-training

content-creator perspective show \
  --voice experienced-lawyer --context legal-training

content-creator perspective verify \
  --voice experienced-lawyer --context legal-training

content-creator perspective approve \
  --voice experienced-lawyer \
  --context legal-training \
  --approved-by "Author"
```

Approval makes no model call. It verifies hashes, creates an immutable version
and approval receipt, and atomically updates only that context.

## Use a perspective

Neutral content can use the voice without any perspective:

```bash
content-creator run \
  "Explain the training schedule" \
  --pack general-text \
  --voice experienced-lawyer
```

Use an approved perspective explicitly:

```bash
content-creator run \
  "Create training material about recognising escalation points" \
  --pack general-text \
  --voice experienced-lawyer \
  --perspective-context legal-training \
  --thesis "Recognition matters more than memorising every rule." \
  --author-supplied
```

The resolved run records exact voice and perspective versions in
`resolved-context.json`. `claim-provenance.json` records direct author
contribution, selected perspective entries, research status, and the rule that
model-proposed framing is not automatically an author position.

The writer and critic receive only the resolved context. The researcher treats
perspective as a hypothesis to support, qualify, or challenge.

## Automatic catalogue resolution

The default remains explicit for backward compatibility. A workspace may opt
into automatic resolution in `content-creator.yaml`:

```yaml
perspective:
  mode: automatic
  allow_multiple: true
  ask_when_ambiguous: true
  show_resolution: true
  conflict_policy: propose-update
```

Store routing metadata at
`profiles/<voice-id>/perspectives/catalogue.json`:

```json
{
  "schema_version": "1.0",
  "routing_only": true,
  "contexts": [
    {
      "context_id": "professional-training",
      "display_name": "Professional training",
      "summary": "Positions about training design and escalation.",
      "use_when": ["training design", "professional escalation"],
      "avoid_when": ["neutral scheduling information"],
      "related_contexts": []
    }
  ]
}
```

The model sees only this catalogue during routing. It may select zero, one, or
several active contexts, subject to workspace policy. The engine validates
every selected id against the active perspective registry, pins exact versions,
and then loads only the selected full perspectives. Catalogue summaries never
become author claims.

Use repeated explicit overrides when needed:

```bash
content-creator run "Create the training piece" \
  --perspective-context professional-training \
  --perspective-context organisational-change
```

Disable perspective use for a run with `--no-perspective`. Resolution is
preserved in `perspective-resolution.json`; resolved versions remain in
`resolved-context.json` and `claim-provenance.json`.

Inspect and verify the catalogue:

```bash
content-creator perspective catalogue --voice experienced-lawyer
content-creator perspective verify-catalogue --voice experienced-lawyer
```

## Publication and updates

Publication never edits an active perspective. When a run uses a perspective
context, the Perspective Extractor may create context-local proposals:

```bash
content-creator perspective proposals \
  --voice experienced-lawyer \
  --context space-law
```

Stage one proposal for review:

```bash
content-creator perspective stage-proposal \
  --voice experienced-lawyer \
  --context space-law \
  --proposal proposal-abc123
```

Review and approve the complete candidate:

```bash
content-creator perspective show \
  --voice experienced-lawyer --context space-law

content-creator perspective approve \
  --voice experienced-lawyer \
  --context space-law \
  --approved-by "Author"
```

This creates a new version. Other contexts and historical runs do not change.
Research findings alone cannot become perspective proposals.

## Changes of mind

Retire an entry by staging a new candidate:

```bash
content-creator perspective retire \
  --voice experienced-lawyer \
  --context space-law \
  --entry perspective-abc123 \
  --reason "The author changed position after further research"
```

Review and approve the candidate normally. The old version remains reproducible.

Deactivate a whole context without deleting history:

```bash
content-creator perspective deactivate \
  --voice experienced-lawyer \
  --context space-law \
  --reason "Context withdrawn"
```

New runs cannot use an inactive context. Historical runs may continue to resolve
their pinned version.

## Blind comparison with ordinary chat

Create the same brief in ordinary chat and save that output as a Markdown file.
Then create a blinded A/B packet:

```bash
content-creator perspective compare-create \
  --run <run-id> \
  --baseline ordinary-chat.md
```

Review `option-a.md` and `option-b.md` without opening `.mapping.json`. Complete
the generated `assessment-template.json`, scoring both options from 1 to 10 for:

- voice authenticity;
- originality of thought;
- factual reliability;
- publishability;
- revision effort and overall preference.

Record and reveal the result:

```bash
content-creator perspective compare-record \
  --run <run-id> \
  --assessment runs/<run-id>/blind-comparison/completed-assessment.json
```

The resulting `assessment-result.json` records which system was preferred. This
tests whether the additional workflow produces author value rather than merely
whether the machinery executes.

## Integrity rules

- Perspective use is optional.
- No implicit cross-context inheritance.
- Every approved entry has provenance.
- Qualifications and counterpositions remain visible.
- Perspective never substitutes for factual evidence.
- First-person positions require direct contribution or approved perspective.
- Publication produces candidates, not active beliefs.
- Approval, versioning, retirement, and deactivation are deterministic.
- Exact perspective versions are part of the run record.
- Repository publication pins selected versions and entry hashes in a tracked,
  privacy-safe receipt. `content-creator verify-publications` checks that
  evidence offline without requiring every piece to select a perspective.
