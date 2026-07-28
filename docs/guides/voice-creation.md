# Voice creation

Only analyse sources that the repository owner is authorised to use. A voice
candidate is separate from an active voice and cannot create content.

## Lifecycle

```text
source material → candidate build → evaluation → human approval
    → immutable active version → superseded or inactive
```

Create and inspect:

```bash
content-creator voice create \
  --name "Example Person" \
  --authorised-by "Repository Owner" \
  --use general-text \
  --sources voice-material/example-person/urls.txt \
  --documents voice-material/example-person/

content-creator voice status example-person
content-creator voice show example-person
content-creator voice verify example-person
```

Approve only after reviewing attribution, evidence limits, patterns,
constraints, and the evaluation report:

```bash
content-creator voice approve example-person --approved-by "Repository Owner"
```

Approval makes no model call. It verifies component hashes, creates an approval
receipt, assigns a stable version, and atomically updates the registry.

Deactivate without deleting history:

```bash
content-creator voice deactivate example-person \
  --reason "Authorisation withdrawn"
```

Pinned historical runs still resolve their saved version. A new explicit
approval is required to reactivate the voice.

`--offline-analysis` exists for deterministic fixtures and development. It
creates only a minimal provisional profile and is not a substitute for
agent-assisted analysis and human review.
