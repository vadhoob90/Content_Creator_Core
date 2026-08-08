# Voice creation

This guide covers the source-derived route for an author who can provide
previous writing. For a new author without suitable material, or to understand
the initial decision checkpoint, start with
[Voice onboarding](voice-onboarding.md).

Only analyse sources that the repository owner is authorised to use. A voice
candidate is separate from an active voice and cannot create content.

The build combines deterministic corpus-stylistic measurements with
evidence-backed agent interpretation. See the
[lightweight linguistic voice framework](linguistic-voice-framework.md) for the
method, limitations, and evaluation model.

## Lifecycle

```text
source material → candidate build → evaluation → human approval
    → immutable active version → superseded or inactive
```

Create and inspect:

```bash
content-creator voice create \
  --voice-id example-person-general \
  --label "Example Person — General" \
  --author-name "Example Person" \
  --author-alias "E. Person" \
  --authorised-by "Repository Owner" \
  --use general-text \
  --sources voice-material/example-person/urls.txt \
  --documents "/absolute/path/to/my-writing"

content-creator voice status example-person-general
content-creator voice show example-person-general
content-creator voice signature example-person-general
content-creator voice verify example-person-general
```

`--documents` accepts a file or directory and may be repeated. Directories are
searched recursively for `.md`, `.txt`, `.docx`, `.pdf`, and `.html` files.
Core reads originals in place; it does not copy or upload them.

Local files supplied through `--documents` are treated as directly authored
when `--authorised-by` confirms the work order. They do not need an embedded
byline, so unpublished drafts and exported documents can be used as voice
evidence. The attestation is recorded in `source-index.json`.

Remote URLs and transcripts still use evidence-based attribution. Do not place
third-party or co-authored material in an attested local document set unless its
contribution is suitable for full voice weighting.

Approve only after reviewing attribution, evidence limits, patterns,
constraints, `linguistic-signature.json`, and the evaluation report:

```bash
content-creator voice approve example-person-general \
  --approved-by "Repository Owner"
```

Approval makes no model call. It verifies component hashes, creates an approval
receipt, assigns a stable version, and atomically updates the registry.

## Evolve an active voice

Adding sources to an active voice preserves its approved profile, constraints,
rubric, and patterns by default. Rebuild, inspect the semantic diff, and approve
the new candidate explicitly:

```bash
content-creator voice add-sources example-person-general \
  --documents "/absolute/path/to/new-writing"
content-creator voice rebuild example-person-general
content-creator voice diff example-person-general
```

Rule changes require an evidence-backed change set. Full regeneration is a
separate explicit replacement mode. See [Safe voice evolution](voice-evolution.md)
for the contracts, commands, and failure-safety guarantees.

Deactivate without deleting history:

```bash
content-creator voice deactivate example-person-general \
  --reason "Authorisation withdrawn"
```

Pinned historical runs still resolve their saved version. A new explicit
approval is required to reactivate the voice.

`--offline-analysis` exists for deterministic fixtures and development. It
creates only a measured provisional rhythm profile and is not a substitute for
agent-assisted interpretation, matched-register comparison, and human review.

The voice ID and label are local configuration. Only `--author-name` and
`--author-alias` values participate in authorship attribution.
