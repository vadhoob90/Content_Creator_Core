# Shared editorial standard

Core supplies a shared baseline for specific, coherent writing that fits the
selected author and audience. The writer applies it during drafting and
revision; the critic uses it to identify concrete weaknesses. Its
[research basis](../research/ai-writing-patterns.md) separates empirical
findings, emerging evidence, and editorial judgment.

## What changes for authors

The [runtime standard](../../contracts/editorial-standard.md) covers generic
openings, inflated vocabulary, abstraction, repetitive rhythm, empty rhetorical
templates, unsupported significance, misplaced certainty, and unnecessary
formatting. It requires criticism to identify a passage, its effect, and a
useful revision direction. It uses the existing rubric dimensions and issue
severity rules. There is no new score, numerical style threshold, automatic
punctuation edit, or authorship classifier.

Keep your own audience, terminology, regional spelling, and author preferences
in the existing repository agents, selected voice, and active learnings.
Explicit author preferences and supported voice habits specialise the shared
style defaults. Integrity boundaries remain mandatory. For example, "avoid em
dashes in my posts" is a valid author preference; "em dashes prove AI use" is
not a supported claim.

Use the existing voice workflow to change an active voice. Do not edit an
immutable voice version or borrow another author's examples to override the
standard. Cross-author or cross-domain policy does not belong in a personal
voice corpus.

An optional instruction for a repository writer or critic could say:

```text
Our audience is practising engineers. Use British English and retain precise
technical terms. The author prefers connected paragraphs and restrained
conclusions. Keep an occasional short sentence when it earns emphasis.
```

These are ordinary instructions in existing local files, not new configuration
keys. There is no need to copy Core's standard into each repository.

## Worked examples

All examples below are constructed. Rewrites may use only the supplied facts;
they are examples of editorial reasoning, not mandatory wording.

| Supplied context | Before | Possible revision | Why |
| --- | --- | --- | --- |
| One approval step was removed; review time fell from five days to two. | In today's rapidly evolving landscape, the team unlocked a transformative new era of review. | The team removed one approval step. Reviews now take two days instead of five. | Starts with the supported change and result. |
| The pilot failed because invitations expired before reviewers opened them. | The pilot failed. The reason? Invitations. They expired. Before reviewers opened them. | The pilot failed because invitations expired before reviewers opened them. | Reconnects the explanation. |
| The team will review applications on Monday. | The implementation of the review of applications by the team will take place on Monday. | The team will review applications on Monday. | Clarifies the actor and action. |
| Twelve people participated; no outcomes are available. | Twelve people joined, underscoring the pilot's transformative impact. | Twelve people joined. Outcome data is not yet available. | Removes an unsupported implication. |
| The change gives reviewers one queue. | This isn't just a change. It's a whole new way of working. | Reviewers now have one queue to check. | Removes an empty contrast. |

Some passages should be preserved. "Save your work. Then close the window."
is a useful pair of short instructions. "The review finished—at last—on
Friday" can fit an author who favours asides. A tool's ability to recommend
edits versus approve publication is a useful contrast. Warranted uncertainty,
literal quotations, code flags, and regional spelling must survive revision.

## Distribution and compatibility

The runtime reads `contracts/editorial-standard.md` from the installed Core
package for every writer and critic prompt, including composition without a
work order. The source copy under `contracts/` is mirrored into the package;
the existing parity test checks they match. Source citations, examples, and
evaluation cases are reference material and are not injected into every draft.

The policy deliberately bypasses workspace resource overrides, as Core role
contracts already do. An old local `rubrics/core.yaml` or a copied contract
cannot hide it. Local agent and voice instructions still enter the prompt.
The `core-editorial` provenance layer records its source and content hash, and
new resolved contexts include an additive `editorial_standard` component hash.
Other roles record a skipped layer and receive no extra writing instruction.

Existing workspaces receive the standard when they install a Core release
containing this change. Updating unrelated repository files does not update
the installed engine. Follow the [dependency upgrade workflow](workspace-dependencies.md)
and verify the writer and critic with `personalisation explain`; their context
should include `core:contracts/editorial-standard.md`. No agent regeneration or
bulk rewriting of author-owned files is required. Existing duplicate local
rules may be reviewed later; explicit preferences should be retained.

The standard is included from Core v1.21.0. Installation and downstream pin
updates are separate operations. Existing drafts and publications are not
rewritten by upgrading. New invocations use the installed guidance and record
its hash; older runs without this layer retain their historical provenance.

## Evaluation set and protocol

[Twelve editorial cases](../../evals/editorial-style.yaml) contain the source
facts, voice constraint, draft, expected action, a reference response, and
preservation requirements. They cover five edits, six preservation cases, and
one evidence gap across the three bundled packs. Cases are passage-level, so
an article example is not expected to satisfy a full article's word count.
The file is also packaged at `evals/editorial-style.yaml` for downstream use.

The cases form a manual editorial evaluation set. They are deliberately
separate from `content-creator eval`, whose fake responses test route behaviour
and cannot establish writing quality. Software tests confirm instruction
delivery, override handling, local-file preservation, and provenance.

For a model evaluation:

1. Use the same case, facts, voice, pack instructions, model version, and
   generation settings for both conditions. In an isolated evaluation harness,
   compare the assembled prompt with the shared editorial section included
   against the same prompt with only that section removed. Do not remove Core
   integrity contracts or change a production workspace to run the comparison.
2. Ask for a revision or preservation decision and a short reason. Evaluate a
   critic separately by checking whether its issue is justified by the case.
   Keep evidence-gap responses in the application's defined output format.
3. Hide the condition labels and randomise pair order for reviewer assessment.
   Repeat cases at least three times per model to observe variability. Treat
   this repeat count as a pilot design choice, not a statistical guarantee.
4. Rate clarity, useful specificity, and voice fit on a 1–5 scale. Record
   factual preservation, correct expected action, unnecessary edits, and the
   reviewer's preferred output (including ties). A reference is illustrative;
   do not score exact wording matches or count dashes as an outcome.
5. Reject any proposed policy revision that introduces unsupported facts or
   damages protected quotation/code/voice features. Review any unnecessary
   edits to preservation cases. Report preference counts and variation by
   case and model; a tiny pilot cannot establish general superiority.

Store trial records with `case_id`, model/version, generation settings,
condition, prompt hash, repeat, output, reviewer, dimension scores,
preservation result, unnecessary edits, and pair preference. Keep author text
private when expanding beyond the supplied synthetic cases.

No live model comparison or independent human preference study has been run
as part of this implementation. Passing offline tests means the standard is
delivered correctly; it does not establish that every future draft will sound
natural. Author review remains part of the workflow.
