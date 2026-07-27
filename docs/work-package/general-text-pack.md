# Configurable general-text pack

## Purpose

`general-text` is both:

- A usable pack for text that does not require channel-specific behaviour
- The versioned base contract for specialised text packs

It prevents every new content type from redefining research, drafting,
validation, review, approval and finalisation.

It does not contain:

- A person’s voice
- Provider or model names
- LinkedIn-specific rules
- External publishing credentials
- Topic knowledge

Those are resolved separately through the voice package, model registry,
content brief and optional distribution adapters.

## Base manifest

```yaml
schema_version: "1.0"
id: general-text
version: "1.0.0"
kind: text

pipeline:
  - optional-research
  - draft
  - deterministic-validation
  - editorial-review
  - bounded-revision
  - human-approval
  - repository-finalisation

defaults:
  output_format: markdown
  objective: explain
  audience: general-professional
  language: en-GB
  length:
    minimum_words: 300
    maximum_words: 1200
  research:
    depth: none
    source: none
  revision_limit: 3

allowed_run_overrides:
  - objective
  - audience
  - language
  - length
  - research
  - structure
  - destination

prompts:
  writer: agents/writer.md
  critic: agents/critic.md

rubrics:
  - rubrics/core.yaml
  - packs/general-text/rubric.yaml

validators:
  - output-schema
  - word-count
  - citation-integrity
  - banned-phrase

model_profiles:
  briefing: fast
  research-light: balanced
  research-deep: deep
  writer: balanced
  critic: balanced
  learning: fast

finalisation:
  adapter: repository
  destination: content/final
  overwrite: false
```

All fields are schema validated. Unknown override fields fail rather than being
silently ignored.

## Using the general pack directly

Conversationally:

> Using Example Person’s voice, create an 800-word technical explainer for a general
> professional audience. Use the general text pack and light research.

CLI:

```bash
content-creator run \
  "Explain how platform engineering changes team responsibilities" \
  --voice example-person \
  --pack general-text \
  --objective explain \
  --audience "technology leaders" \
  --length 700:900 \
  --research light
```

Or with a brief:

```yaml
request: Explain how platform engineering changes team responsibilities
voice_id: example-person
content_pack: general-text
objective: explain
audience: technology leaders
pack_options:
  length:
    minimum_words: 700
    maximum_words: 900
  research:
    depth: light
    source: agent
```

```bash
content-creator run --brief briefs/platform-engineering.yaml
```

## Specialising the pack

Specialised text packs extend exactly one base pack. Arbitrary multiple
inheritance is not supported.

```yaml
schema_version: "1.0"
id: linkedin-post
version: "1.0.0"
extends:
  pack: general-text
  version: "1.0.0"

defaults:
  audience: professional-network
  length:
    minimum_words: 50
    maximum_words: 600

allowed_run_overrides:
  - objective
  - audience
  - length
  - research

rubrics:
  append:
    - packs/linkedin-post/rubric.yaml

validators:
  append:
    - no-hashtags
    - linkedin-format

finalisation:
  destination: content/linkedin/posts/final
```

Resolution order:

```text
general-text manifest
    → specialised-pack overrides
    → schema-approved run overrides
```

Integrity validators cannot be removed by a specialised pack or run override.

## Creating a configured pack

```bash
content-creator pack create internal-blog \
  --extends general-text

content-creator pack validate internal-blog
content-creator pack show internal-blog --resolved
content-creator pack list
```

The create command scaffolds:

```text
packs/internal-blog/
├── pack.yaml
├── rubric.yaml
├── validators.yaml
├── evals/
└── README.md
```

## Boundaries

- Destination paths must remain inside configured workspace roots
- Packs cannot select credentials
- Packs request capability profiles, not vendor model IDs
- Packs cannot activate voices
- Packs cannot weaken personal-integrity, provenance or phrase-overlap gates
- Pack changes are versioned; old runs retain the resolved prior version
- External distribution is outside the first release

## Tests

The general pack requires:

- Manifest schema tests
- Default resolution
- Every allowed override
- Rejection of unknown overrides
- Rejection of invalid length and research combinations
- Destination path containment
- Integrity-validator preservation
- Single-base inheritance
- Specialised-pack isolation
- Immutable resolved-context snapshot
- Direct end-to-end content run

A fixture specialised pack proves the extension contract before LinkedIn is
migrated. LinkedIn post and one non-LinkedIn pack then prove real-world reuse.
