---
name: voice-builder
description: Create, inspect, evolve, evaluate, approve, pause, reactivate, retire, or restore an evidence-backed writing voice from authorised URLs, publications, text, HTML, PDF, DOCX, transcripts, and reviewed learning in a Content Creator repository. Use when a user asks to create or upgrade someone's voice, add voice sources, consolidate learning, approve a voice, check voice status, stop using a channel, or change which voice version may create content.
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
2. Ask whether statistical voice scoring should be disabled, deterministic, or
   ML-based for this voice. Do not silently enable it. Explain that deterministic
   scoring needs no training, while ML requires a separately authorised matched
   comparison corpus after voice activation. Starter voices cannot use scoring.
3. Put URLs in a text file and private documents outside Git-tracked paths.
4. Run:

```bash
content-creator voice create \
  --name "<display name>" \
  --authorised-by "<approver>" \
  --use general-text \
  --sources "<URL file>" \
  --documents "<document directory>" \
  --statistical-voice-score deterministic \
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

## Compute a statistical voice score

When the author asks to score a draft without changing automatic settings, run:

```bash
content-creator voice score <voice-id> \
  --draft "<draft path>" \
  --method deterministic
```

Use `--method ml` only when a trained model exists. The output always identifies
the method, score, reliability, evidence coverage, observations, and claim
limits. Never present the number without its method and reliability context.

To change automatic scoring later, use:

```bash
content-creator voice score-config <voice-id> \
  --enable \
  --method deterministic \
  --selected-by "<author>"
```

Use `--disable` to turn it off. Automatic scores remain critic-only advisory
evidence and have no direct quality-gate weight.

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
voice-scoped choice with `voice score-config <voice-id> --enable --method ml`.

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
content-creator voice diff <voice-id>
```

When a voice is active, rebuild evolves its immutable approved baseline by
default. It preserves approved profile prose, constraints, rubric, and patterns;
new evidence may add non-conflicting proposals. Always show the semantic diff
before asking for approval.

Use an evidence-backed `--change-set` for an intentional rule modification,
supersession, or removal. Every changed rule needs authorised source IDs,
confidence, and rationale, followed by author review. Never use
`--full-regenerate` unless the user explicitly asks to replace the approved
guidance.

## Upgrade an immutable voice version

Do not use routine rebuild as a substitute for governed evidence and learning
selection. Plan first:

```bash
content-creator voice upgrade-plan <voice-id> --mode incremental
```

Show the active version and strategy, evidence cutoff, canonical evidence
delta, duplicates, active or conflicting learning, conservative classification
proposals, provider implications, and exact approval points. Incremental mode
is the default and must not retrieve, analyse, or transmit the historical
baseline corpus text.

When active prior-version learning exists, open the generated selection
template and require the author to review every disposition. Only
`voice-profile`, `voice-constraint`, and `critic/rubric` may be incorporated.
Keep researcher policy, perspectives, visual preferences, and repository-agent
policy in their own lifecycle. Never activate, silently rescope, delete, or
promote a learning record on model judgement alone.

Build with a stable retry key:

```bash
content-creator voice upgrade <voice-id> \
  --mode incremental \
  --learning-selection profiles/<voice-id>/upgrade/learning-selection.json \
  --idempotency-key <stable-key>
content-creator voice diff <voice-id>
```

Use `--mode full-corpus` only after explaining source count, provider, cost,
privacy, and historical-corpus sharing. It preserves the active baseline by
default. It is not full replacement. After approval, report the frozen prior
learning epoch, fresh new-version epoch, incorporated IDs, carry-forward IDs,
and receipt hashes.

## Approve deterministically

Only after explicit human approval, run:

```bash
content-creator voice approve <voice-id> --approved-by "<approver>"
```

Report the activated version from the receipt. Do not substitute an LLM call,
file edit, or registry edit for this command.

## Pause, retire, or restore

Pause when the author may return. Retire when the channel is no longer part of
future work. Always inspect persisted state first:

```bash
content-creator voice retirement-plan <voice-id>
content-creator voice deactivate <voice-id> \
  --deactivated-by "<author>" --reason "<reason>"
content-creator voice reactivate <voice-id> --approved-by "<approver>"
content-creator voice retire <voice-id> \
  --retired-by "<author>" --reason "<reason>" --plan-hash sha256:<hash>
```

Surface required default, candidate, context, proposal, learning, and unfinished-run
decisions. Do not select a replacement default or silently cascade perspective
retirement. Pause and retirement freeze the learning epoch and preserve all history.
Reactivation verifies the same immutable version and opens a new activation epoch;
it does not create another voice version.

A retired voice cannot use reactivation. Generate `voice restore-plan`, review its
hash, and use `voice restore` with explicit requester and approver identities. Use
`voice verify-lifecycle` for offline receipt verification. Never describe retirement
as deletion.
