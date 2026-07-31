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

## Optional statistical voice score

Core can compute a `statistical_voice_score` for a draft through either a
deterministic corpus-distribution method or an optional ML classifier. This
feature is disabled by default and remains advisory: it does not change
validation errors, quality scores, or publication gates. When enabled, the
per-revision report is stored as
`runs/<run-id>/statistical-voice-score-<revision>.json` and supplied only to the
critic. The writer never receives numerical targets.

Automatic scoring has two independent gates. The workspace or selected voice
must enable scoring, and the selected content pack must explicitly declare
itself eligible. Both conditions are required. Core's `linkedin-article` pack
is eligible; `linkedin-post` and the mixed `general-text` pack are not. For an
ineligible pack, Core creates no score artifact and supplies no score to the
critic, even when the voice preference is enabled.

New source-derived voices choose disabled, deterministic, or ML scoring during
the guided voice-creation workflow. The choice is stored under
`profiles/<voice-id>/statistical-voice-score.json`, so voices in the same
workspace can use different methods. Change it later with:

```bash
content-creator --workspace . voice score-config <voice-id> \
  --enable --method deterministic --selected-by "<author>"
```

Use `--disable` to turn automatic scoring off. Workspace defaults and
deterministic thresholds remain configurable in `content-creator.yaml`:

```yaml
statistical_voice_score:
  enabled: false
  method: deterministic
  minimum_sources: 20
  minimum_draft_words: 100
  outlier_iqr_multiplier: 1.5
  max_reported_outliers: 8
```

Pack authors opt a sufficiently long-form pack into automatic scoring in its
`pack.json`:

```json
"statistical_voice_score": {"eligible": true}
```

Eligibility is fail-safe off when the field is omitted. Enable it only after
the pack's draft length and matched reference evidence are sufficient for a
stable comparison. Voice or workspace configuration cannot override an
ineligible pack.

An explicit offline score is available regardless of the automatic setting:

```bash
content-creator --workspace . voice score <voice-id> \
  --draft path/to/draft.md --method deterministic
```

The deterministic score is a 0–100 compatibility measure. It penalises only
distance beyond the configured interquartile-range envelopes; values anywhere
inside an envelope receive the same treatment, so moving toward the corpus
centre cannot improve the score. The report also preserves material outliers,
reliability, evidence coverage, and claim limits. Too-small corpora and short
drafts return an insufficient-evidence status and no score.

## Optional machine-learning classifier

Machine-learning training is a separate, explicit author action. It is local
and makes no provider call. It never runs
during voice building, content generation, workspace initialisation, or package
installation. Install the optional training dependency and supply a matched
non-author comparison corpus:

```bash
python -m pip install 'content-creator[ml]==<the-workspace-pinned-version>'

content-creator --workspace . voice train-ml <voice-id> \
  --comparison-documents /absolute/path/to/matched-comparison-writing
```

Core trains one regularised logistic-regression classifier from the active
voice's written feature vectors and the supplied comparison documents. Raw
source text and comparison paths are not stored in Core or in the model. The
author workspace receives a version-scoped JSON artifact under
`profiles/<voice-id>/models/<voice-version>/` containing the feature schema,
scaler values, coefficients, data fingerprints, evaluation results, and
reliability assessment. Inference reads that JSON directly and does not load a
pickle or require scikit-learn.

Training reliability is reported before fitting. These are conservative volume
heuristics, not proof that the documents are independent, representative, or
correctly matched:

- fewer than 10 documents or 5,000 words in either class refuses training;
- fewer than 40 documents or 20,000 words in either class produces a prominent
  low-confidence warning and does not train by default;
- after reviewing that warning, the author may explicitly repeat the command
  with `--accept-low-confidence`;
- a class imbalance greater than 2:1 also requires explicit acceptance.

Training never activates the classifier. After reviewing its evaluation, the
author separately opts into ML scoring:

```bash
content-creator --workspace . voice score-config <voice-id> \
  --enable --method ml --selected-by "<author>"
```

Use `voice score <voice-id> --draft <path> --method ml` for an explicit score.
The ML and deterministic values share a 0–100 display scale but are not directly
interchangeable: deterministic scoring measures compatibility with observed
author ranges, while ML measures compatibility with the author corpus relative
to the supplied comparison corpus. Every result therefore retains its method.
The score remains advisory, is supplied only to the critic, and is not an
authorship probability, validation error, direct rubric weight, or publication
gate.

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
