# Adopt author edits without rewriting

Use `adopt-edit` when you have edited a reviewed, unpublished draft yourself.
Core preserves your exact UTF-8 text, records the original and a diff, runs
local deterministic checks, and refreshes the production manifest and review
copy. It does not invoke a writer, critic, research provider, or learning
extractor.

Read the accepted draft hash from `runs/<run-id>/draft-integrity.json`. For an
older run without that file, use the `final-draft` artifact hash from its
production manifest. The expected hash identifies the accepted predecessor,
not the newly edited file.

```bash
content-creator adopt-edit <run-id> \
  --draft-file edited.md \
  --expected-sha256 sha256:<accepted-draft-hash> \
  --idempotency-key author-edit-01
```

The source may be a separate file or the run's edited `final.md`. For in-place
edits Core must recover a retained original matching the accepted hash. If the
original is unavailable, supply it with `--baseline-file original.md`; a hash
alone cannot reconstruct missing text. Core refuses to overwrite a different
concurrent edit. Reuse the same idempotency key only for an identical request;
a later edit requires a new key and the newly accepted hash.

## Review changed claims

Only changes to trailing newline characters can retain the earlier claim
clearance automatically. All other edits conservatively require author claim
review, even when they may be stylistic. Changed research also reopens review.
This deliberately avoids treating keyword matching as proof of unchanged
meaning. Deterministic validation errors also leave the run in `needs_author`.

To supply new research, add `--research-file research.json` to `adopt-edit`.
The input must follow the existing typed `ResearchBrief` contract. Core
validates and records it without performing research or changing the original
work order's research route. The production manifest separately records the
current research hash in `draft_integrity`.

Inspect the diff, adopted text, research, and `draft-integrity.json`. Once the
author has reviewed the claims and supporting evidence, record the decision:

```bash
content-creator approve-edit-claims <run-id> \
  --draft-sha256 sha256:<current-draft-hash> \
  --research-sha256 sha256:<current-research-hash> \
  --approved-by "Author" \
  --notes "Reviewed the changed claims against the supplied evidence."
```

Omit `--research-sha256` only when there is no research artifact. Approval
requires the exact current hashes and passing deterministic checks. It does
not invoke a provider, rewrite the adopted text, publish, or activate learning.
A changed draft or research artifact invalidates the decision. The coordinator
surfaces outstanding claim review before offering publication.

`revise --draft-file` remains the model-backed critique route. New prose
revisions also receive draft-bound claim-review protection; a passing critic
score cannot silently approve changed factual meaning.

## Evidence and historical policy

- `accepted/rNNNN.md` retains the exact accepted text.
- `accepted/rNNNN.manifest.json` retains the first manifest for that revision.
- Adoption preserves available predecessor research under
  `accepted/rNNNN.research.json` before replacing current research.
- `revision-baseline-NN.md` and `revision-NN.diff` describe the edit.
- `validation-NN.json` records deterministic results and the validation engine
  version. Earlier critic/quality artifacts remain historical; adoption does
  not manufacture a new model quality score.
- `draft-integrity.json` binds text, research, review state, and author decisions.
- `claim-review-NN.json` records explicit approval of changed claims.

New generation contexts retain a hash-bound effective pack snapshot. Adoption
uses those original inputs even after the installed pack changes. Older runs
may use a verified unchanged standalone pack; incomplete inherited-policy
history requires restoring the original effective inputs. Missing historical
inputs are not silently replaced by the latest installed policy. Original
voice and perspective references remain pinned in the work order.

## Recovery

Adoption, claim approval, revision, and publication share an exclusive run lock.
An adoption or claim-approval write failure restores the touched artifacts to
their exact pre-operation bytes. A process interruption leaves a run-local
`author-edit-transaction.json`; further revision/publication is blocked until
explicit recovery:

```bash
content-creator recover-edit <run-id>
```

Recovery restores only the paths listed in the journal. Review and preserve any
manual edits made after interruption before invoking it. If a stale lock
remains, follow the existing operations recovery guidance to inspect its owner;
Core never removes a possibly live lock automatically. Journals contain private
run text and must remain with ignored run evidence.

This implements the author-edit integrity slice of issue #135. Multiple visual
slots, bundle membership, and draft export remain subsequent work.
