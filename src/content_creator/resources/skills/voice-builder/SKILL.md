---
name: voice-builder
description: Create, inspect, evaluate, approve, deactivate, or reactivate an evidence-backed writing voice from authorised URLs, text, HTML, PDF, DOCX, and transcript sources in a Content Creator repository. Use when a user asks to create someone's voice, add voice sources, approve a voice, check voice status, or change which voice version may create content.
---

# Voice Builder

Work from the repository root. Never claim that a candidate is active until the
deterministic approval command succeeds.

## Decide whether another voice is needed

Do not equate a new subject with a new voice. Ask whether the new material has a
meaningfully different register, audience, channel, or source corpus.

- Create a separate voice when those stylistic conditions differ and isolation
  is useful.
- Create or select a perspective context when the author communicates in the
  same voice but needs separate subject-matter positions or expertise.

Show the proposed choice and rationale. Never create a new voice or perspective
silently.

## Create a candidate

1. Confirm that the user is authorised to analyse the sources.
2. Put URLs in a text file and private documents outside Git-tracked paths.
3. Run:

```bash
content-creator voice create \
  --name "<display name>" \
  --authorised-by "<approver>" \
  --use general-text \
  --sources "<URL file>" \
  --documents "<document directory>" \
  --provider codex-native
```

Use native subscription execution by default in an interactive Codex session.
Respect an explicit provider choice and never fall back from native mode to
API-key billing.

The command ingests, attributes, assesses, analyses, criticises, builds, and
evaluates the candidate. A passing candidate must stop at `awaiting_approval`;
an insufficient candidate remains `built` with actionable gaps.

The build creates `linguistic-signature.json` using the repository's lightweight
corpus-stylistics framework. It reports attribution-weighted measurements and
keeps spoken and written registers separate. Treat these measurements as
descriptive evidence, never as proof of authorship or rigid generation targets.

## Train an optional ML classifier

Never train or activate an ML classifier during ordinary voice creation. Use
this path only when the author explicitly asks to train one and supplies an
authorised, matched non-author comparison corpus.

Run:

```bash
content-creator voice train-ml <voice-id> \
  --comparison-documents "<comparison directory>"
```

The command performs a reliability preflight before fitting. If it returns
`insufficient_data`, do not train. If it returns
`warning_confirmation_required`, show every warning and stop. Use
`--accept-low-confidence` only after the author explicitly accepts those
warnings in a separate instruction. Training creates a version-scoped JSON
artifact but never enables it.

After the author reviews the evaluation, enable use only through their explicit
workspace choice:

```yaml
voice_assessment:
  enabled: true
  mode: ml
```

The classifier score remains critic-only advisory evidence. Never call it an
authorship probability, use it as a publication gate, or feed numerical targets
to the writer.

## Review and improve

Run:

```bash
content-creator voice status <voice-id>
content-creator voice show <voice-id>
content-creator voice signature <voice-id>
content-creator voice verify <voice-id>
```

Show the profile, evidence limits, source attribution, linguistic signature,
provisional patterns, and evaluation failures. Do not call an observed feature
distinctive unless a matched-register reference comparison supports that claim.
To add material:

```bash
content-creator voice add-sources <voice-id> --sources "<URL file>"
content-creator voice rebuild <voice-id>
```

## Approve deterministically

Only after explicit human approval, run:

```bash
content-creator voice approve <voice-id> --approved-by "<approver>"
```

Report the activated version from the receipt. Do not substitute an LLM call,
file edit, or registry edit for this command.

## Deactivate or reactivate

Run the deterministic command matching the user's explicit instruction:

```bash
content-creator voice deactivate <voice-id> --reason "<reason>"
content-creator voice reactivate <voice-id> --approved-by "<approver>"
```

Deactivation blocks future unpinned runs but preserves historical versions.
Reactivation creates a new approval receipt.
