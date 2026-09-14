# Linguistic research: generic AI writing and editorial quality

Research date: 14 September 2026. Scope: an applied literature review for
English-language Content Creator drafts, with a current-source check through
that date. This is a targeted review, not an exhaustive systematic review or a
new corpus experiment. The recommendation is to evaluate meaning and voice in
context, rather than classify authorship from stylistic features.

## Method and evidence labels

Searches covered lexical overrepresentation, grammatical and rhetorical
variation, punctuation, sentence length, and detector false positives. Primary
papers and publisher guidance were prioritised over popular lists of "AI
words". Peer-reviewed studies, preprints, and professional editorial advice
are identified separately below. Full text was inspected for Reinhart et al.
and Freeburg; the other research summaries rely on the linked author/publisher
abstracts. The AP source is editorial guidance, not an experiment.

Three labels separate claims that otherwise easily become confused:

- **Empirical, scoped:** observed in the particular models, language, corpus,
  and prompts studied. This does not establish a universal writing rule.
- **Emerging:** a recent preprint or limited experiment that merits attention
  but does not support a causal explanation or production threshold.
- **Editorial judgment:** a useful revision principle whose value depends on
  the reader, author, and task. It is not a demonstrated AI signature.

No word-frequency threshold, detector accuracy claim, or universal sentence
length rule is inferred from these sources. No downstream author material was
uploaded, and no private author corpus was used for this review.

## What the research supports

### Lexical concentration: meaningful at corpus level

Juzek and Ward identify 21 words with unusual increases in scientific abstracts
and investigate possible explanations for their overrepresentation in LLM
output. Their results suggest a possible role for human-feedback training, but
do not settle the mechanism. This supports monitoring habitual vocabulary in
context, not banning individual words. **Empirical, scoped; COLING 2025.**
[Juzek and Ward, “Why Does ChatGPT ‘Delve’ So Much?”](https://aclanthology.org/2025.coling-main.426/)

Kobak and colleagues analyse vocabulary changes in biomedical abstracts and
estimate a lower bound of 13.5% LLM processing in 2024 under their method's
assumptions. Their unit of inference is a population of abstracts. The result
cannot establish whether a particular writer used AI, and biomedical vocabulary
does not automatically transfer to professional social posts.
**Empirical, scoped; Science Advances 2025.**
[Kobak et al., “Delving into LLM-assisted writing…”](https://arxiv.org/abs/2406.07016)

Practical inference: ask whether a word conveys something precise in this
sentence. Replacing every "delve" with "explore" leaves empty claims empty.
Terms such as "robust" may be necessary technical vocabulary.

### Grammar and register: more useful than punctuation alone

Reinhart and colleagues compare parallel human/model texts across genres using
GPT-4o and Llama 3 variants. Instruction-tuned models show stronger stylistic
departures than base models, including preferences for participial clauses and
nominalisations. Some features move in different directions across model
families. The study supports genre-sensitive review of noun-heavy abstraction
and clause patterns; its models do not represent every current system.
**Empirical, scoped; arXiv version 2, August 2025.**
[Reinhart et al., “Do LLMs write like humans?”](https://arxiv.org/html/2410.16107v2)

Zamaraeva and colleagues compare six LLMs with human New York Times writing
using a formal grammar. They find systematic differences in grammatical-type
distributions within that news genre. This is further evidence for studying
syntax, with limited grounds for transfer to an individual author's voice.
**Empirical, scoped; ACL 2025.**
[Zamaraeva et al., formal syntactic comparison](https://aclanthology.org/2025.acl-long.443/)

Practical inference: inspect patterns such as "..., underscoring the importance
of ...". The problem may be an unsupported inference, an unclear actor, or
repetition. Participial clauses themselves remain legitimate grammar.

### Dashes: a contextual signal with substantial limits

The AP Stylebook explicitly rejects treating an em dash as proof of AI writing
and explains its ordinary editorial use. This is relevant professional advice,
not statistical evidence. **Editorial guidance; August 2025.**
[AP Stylebook on dashes and AI](https://www.apstylebook.com/blog_posts/24)

Freeburg's March 2026 preprint reports different em-dash rates and different
responses to formatting-suppression prompts across twelve models. This is
useful emerging evidence against a universal dash rule. The proposed connection
to Markdown training is a hypothesis; behavioural observations alone do not
establish the training mechanism. **Emerging; arXiv preprint.**
[Freeburg, “The Last Fingerprint”](https://arxiv.org/html/2603.27006v1)

Czuma's August 2026 preprint studies 146,239 congressional press releases and
reports a rise in unspaced em dashes, especially in 2025. The abstract discloses
a breached preregistered validation gate and presents the LLM interpretation
as exploratory. It explicitly disclaims individual-text detection and causal
inference. **Emerging; arXiv preprint.**
[Czuma, congressional press-release study](https://arxiv.org/abs/2608.05889)

Practical inference: distinguish an em dash (—), en dash (–), hyphen (-), and
double hyphen (--). Inspect interruptions and typography in their context.
Replacing every dash with a full stop can worsen rhythm and meaning. A house
style preference against em dashes is valid as an author preference.

### Sentence length and detection: avoid universal claims

The reviewed evidence does not establish "very short sentences" as a universal
AI signature. Sentence length alone misses syntax, rhythm, purpose, and genre.
Repeated fragments can become monotonous, while a short instruction can be
exactly right. Review the passage and its intended audience rather than enforce
a mean, minimum, or prescribed alternation. **Editorial judgment informed by
the scoped grammatical studies above.**

Liang and colleagues report that detectors tested in their 2023 English study
frequently misclassified non-native writing. That finding is a reason to protect
language variation, not a claim that every detector in every language behaves
the same way. **Empirical, scoped; Patterns 2023.**
[Liang et al., detector bias study](https://arxiv.org/abs/2304.02819)

Al Ali and colleagues revisit this issue in Czech and find no systematic bias
across three detector families. Their 2026 paper illustrates why language, time,
and detector choice matter. It does not negate the earlier English result.
**Empirical, scoped; author manuscript, accepted to EACL 2026 Student Research
Workshop.**
[Al Ali et al., “Different Time, Different Language”](https://arxiv.org/abs/2602.05769)

Core therefore evaluates editorial quality and voice fit. It does not predict
authorship, certify text as human, or target detector evasion.

## Practical review inventory

These are candidates for contextual review, not automatic violations. The
research does not establish a universal prevalence for the editorial rows.

| Pattern | Evidence status | Useful review question | Legitimate use to preserve |
| --- | --- | --- | --- |
| Recurring inflated vocabulary | Empirical, scoped | Does this word add precision? | Domain terminology; author vocabulary |
| Noun-heavy abstraction | Empirical, scoped | Who does what, and can that be stated clearly? | Formal concepts; technical definitions |
| Trailing significance clauses | Scoped grammar evidence; editorial interpretation | Does the evidence support this consequence? | Real relationships and qualifications |
| Repeated dash interruptions | Emerging; editorial interpretation | Does the interruption clarify the main thought? | Deliberate voice; quotation; house style |
| Strings of punchy fragments | Editorial judgment | Does the rhythm interrupt the argument? | Urgent instructions; terse voice |
| Uniform sentence/paragraph shapes | Editorial judgment | Is the pattern serving this passage? | Parallel instructions or comparisons |
| "Not X, but Y" framing | Editorial judgment | Is there a real, useful distinction? | Correction of a likely misunderstanding |
| Repeated triples or question/answer hooks | Editorial judgment | Does the structure carry information? | Genuine three-part content; teaching |
| Generic openings and grand claims | Editorial judgment | Can the piece begin with its actual subject? | Necessary background for the audience |
| Stock transitions and repeated conclusions | Editorial judgment | Is there a new relationship or useful summary? | Long-form navigation and synthesis |
| Generic praise or promotional intensity | Editorial judgment | Is the evaluation warranted and voice-appropriate? | Supported enthusiasm; promotional brief |
| Habitual hedging or forced certainty | Editorial judgment | Does confidence match the evidence? | Real uncertainty and attribution |
| Overformatted headings, bold, and lists | Editorial judgment; emerging model observations | Does this format help readers use the content? | Accessible instructions and comparisons |
| Invented personal texture or anecdotes | Core integrity boundary | Is this authorised and supported? | Documented author experience |

## Translation into Core

The [shared editorial standard](../../contracts/editorial-standard.md) turns
these findings and explicitly labelled editorial judgments into writer and
critic guidance. Author preferences and supported voice evidence specialise
its defaults. Existing integrity rules continue to govern facts and claims.

The [implementation and evaluation guide](../guides/editorial-standard.md)
explains distribution, local preferences, worked examples, and the evaluation
protocol. The examples are constructed teaching material, not samples from
the cited studies and not validated evidence of an improvement in model output.

## Maintenance and open questions

Revisit the evidence when changing the shared standard or adopting a major
provider/model revision. Compare actual drafts across the installed models and
supported packs before adopting a new heuristic. Track false positives and
author rejection of edits as well as successful improvements. Extend the
evidence base before applying English findings to another language.

Open questions include whether the standard improves blind reader preference,
whether it preserves distinct author voices over repeated revisions, and how
robustly different models obey it. Those require generation and human review;
the offline software tests only establish delivery, provenance, and isolation.
