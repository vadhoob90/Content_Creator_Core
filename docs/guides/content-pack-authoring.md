# Content-pack authoring

Create a pack that extends the single `general-text` base:

```bash
content-creator pack create internal-briefing --extends general-text
content-creator pack validate internal-briefing
content-creator pack show internal-briefing --resolved
```

A pack owns its format, destination, defaults, prompts, rubric additions and
validators. It may request capability profiles but cannot name provider models,
select credentials, activate voices, or remove the base integrity validators.

Visual support is also pack-owned and disabled by default. A pack may declare
provider-independent execution capabilities and platform rules:

```json
"visuals": {
  "supported": true,
  "required": false,
  "execution_classes": ["deterministic", "generative"],
  "aspect_ratios": ["1:1", "4:5"],
  "formats": ["png", "jpg"],
  "max_file_size_bytes": 8388608,
  "safe_areas": [],
  "crop_profiles": [],
  "destination": "content/example/visuals"
}
```

Packs define platform semantics, never author-specific palette, typography, or
brand voice. Core validates the resolved profile and routes a typed brief to a
registered adapter. See [Visual asset workflows](visual-assets.md).

Statistical voice scoring is also a pack-owned eligibility decision and is
off by default. A sufficiently long-form pack can opt in with:

```json
"statistical_voice_score": {"eligible": true}
```

This does not enable scoring by itself: the selected voice or workspace must
also opt in. Ineligible packs never create a score artifact or pass a score to
the critic. Do not enable the field for short-form or mixed-format packs merely
because their maximum word count can be large.

Resolution order is deterministic:

```text
general-text → one specialised pack → schema-approved run overrides
```

Unknown overrides, inheritance cycles, multiple base levels, invalid word
ranges and destinations outside the repository fail before a run is created.
Add replay cases for each supported research route and an isolation test proving
that another pack does not receive the new rules.
