# Lightweight linguistic voice framework

Content Creator uses corpus stylistics to make a voice profile more
evidence-based, consistent, and reviewable. It does not perform forensic
authorship attribution and does not claim that measured features are unique to
a person.

## Method

```text
authorised source
    → attribution and speaker isolation
    → register classification
    → deterministic linguistic measurements
    → evidence-backed pattern interpretation
    → independent criticism
    → held-out evaluation
    → human approval
```

The framework examines five dimensions:

1. **Register and context** — source type, spoken or written mode, channel,
   audience, and purpose where known.
2. **Discourse structure** — openings, progression, examples, contrast,
   qualification, and conclusions.
3. **Stance and relationship** — reader address, first-person reference,
   questions, modal verbs, hedges, and emphasis.
4. **Syntax and rhythm** — sentence and paragraph distributions, short and long
   sentence ratios, and punctuation.
5. **Lexical choices** — contractions, connective patterns, and moving
   type-token lexical diversity.

The deterministic output is stored in `linguistic-signature.json` inside each
voice candidate and immutable active version. It includes:

- per-source features;
- attribution weights;
- separate spoken and written aggregates;
- separate source-kind aggregates;
- medians, interquartile ranges, minima, maxima, and weighted means;
- explicit cautions and comparison limitations.

Inspect the candidate signature without opening repository files directly:

```bash
content-creator voice signature <voice-id>
```

## Optional draft assessment

Core can compare a draft with the resolved active voice's written linguistic
distribution. This feature is disabled by default and remains advisory: it does
not change validation errors, quality scores, or publication gates. When enabled,
the per-revision report is stored as
`runs/<run-id>/voice-assessment-<revision>.json` and supplied only to the critic.
The writer never receives numerical targets.

Enable automated assessment in `content-creator.yaml`:

```yaml
voice_assessment:
  enabled: true
  minimum_sources: 20
  minimum_draft_words: 100
  outlier_iqr_multiplier: 1.5
  max_reported_outliers: 8
```

Disable it by setting `enabled: false` or omitting the section. An explicit
offline comparison is available regardless of that automation setting:

```bash
content-creator --workspace . voice assess <voice-id> --draft path/to/draft.md
```

The assessment reports only material outliers beyond the configured
interquartile-range envelope. It deliberately produces no authorship probability
or aggregate similarity score. Too-small corpora and short drafts return an
insufficient-evidence status instead of a misleading result.

## Measurements are evidence, not instructions

The writer must not mechanically target an average sentence length or repeat
every observed mannerism. Measurements describe a distribution in the
authorised corpus. The Voice Analyst interprets possible communicative
functions, while the Profile Critic rejects rigid, unsupported, generic, or
caricatured conclusions.

A voice pattern records:

- its linguistic category;
- an observable description;
- a separately identified functional interpretation;
- supporting and counterexample source IDs;
- contexts where it is supported;
- cautious generation guidance;
- an anti-pattern;
- measured linguistic evidence;
- confidence and confirmation status.

## Attribution weighting

Directly authored material receives full evidential weight. Co-authored and
interview material receives less weight. For speaker-labelled transcripts, only
the target person's turns are analysed. The original normalised source remains
available for audit and phrase-overlap protection.

Corpus sufficiency uses attribution-weighted analysable words. A candidate
requires at least 500 weighted words. This is a minimum build gate, not a claim
that 500 words are enough for a high-confidence voice.

## Register and comparison limits

Spoken and written language are reported separately because people adapt their
language to context. A feature observed in a LinkedIn post may be a platform
convention rather than a personal characteristic.

The current signature explicitly records that no matched-register reference
corpus was supplied. Until comparable baseline material is added, patterns may
be described as `observed`, but not `distinctive` or `unique`.

The stance and connective lexicons in version 1.0 are English-specific.
Sentence, paragraph, and punctuation measures can still be reported for other
languages, but non-English lexical interpretation requires a future
language-specific extension.

## Evaluation

The candidate reserves an eligible source as held-out material. The evaluator
checks:

- transfer to an unseen topic;
- adaptation across supported channels;
- rejection of generic output;
- natural variation rather than metric matching;
- resistance to mannerism stacking;
- absence of unsupported personal context;
- absence of material phrase copying.

Model evaluation remains supporting evidence. Human approval is required before
activation, and blind comparison with ordinary chat remains the strongest
practical test of authenticity.

## Privacy and ethical boundary

Linguistic features must not be used to infer protected characteristics,
identity, biography, personality, beliefs, or mental state. Analyse only
authorised material and deactivate a voice if authorisation is withdrawn.
