# Publication provenance and CI verification

Core writes a compact, repository-tracked receipt beside its ignored run
evidence whenever repository publication succeeds. The receipt binds the
published bytes to the originating run, pinned voice, direct author input,
selected perspective versions and entries, and the exact deterministic
perspective evaluation used at the publication boundary.

New receipts also contain an `artifacts` collection for the complete approved
communication package. The canonical text entry retains the legacy
`artifact_path` and `artifact_hash` contract, while each media entry adds its
role, source and published paths, SHA-256 hash, MIME type, dimensions, alt text,
approval state, asset ID, parent asset ID, and derivation revision.

Receipts live under `publication-receipts/` by default. They contain hashes and
minimal provenance classifications, not prompts, drafts, feedback, research
notes, or author-contribution text.
New receipts also record the resolved content pack ID and version. The
[production manifest](production-manifests.md) provides the broader run summary
and review-only table without decorating the published content. New receipts
bind its stable generation-time governance hash and run-local path; mutable run
status and publication metadata remain outside that hash.

## Verify publications offline

Run the verifier in a workspace or in CI:

```bash
content-creator verify-publications
```

The command makes no provider or network call. It checks publication hashes,
receipt schemas, originating status, pinned voice manifests, perspective
manifests, approved entry hashes, the recorded deterministic evaluation, and
every package artifact's bytes and required image metadata. For new receipts it
also recomputes the production governance hash from the referenced manifest.
An inactive context cannot authorize a new publication; historical receipts
continue to verify their immutable version after a later deactivation.

Configure enforcement in `content-creator.yaml`:

```yaml
publication_provenance:
  policy: required-for-new-publications
  receipts_directory: publication-receipts
  semantic_review: selected-perspectives
```

Supported policies are:

- `off`: skip verification;
- `advisory`: report findings and exit successfully;
- `required-for-new-publications`: require receipts except for an unchanged
  legacy baseline;
- `required`: require valid receipts for every configured publication.

New generated workspaces use prospective enforcement with an empty baseline.
Existing workspaces remain advisory until deliberately migrated.

### Verify one current publication

Repository-wide verification remains the CI default. Operational checks can be
scoped to one publication so legacy debt does not obscure a new valid package:

```bash
content-creator verify-publications --run-id <run-id>
content-creator verify-publications --artifact content/linkedin-post/published/post.md
content-creator verify-publications \
  --receipt publication-receipts/content/linkedin-post/published/post.md.receipt.json
content-creator verify-publications --new-only
```

The four scope options are mutually exclusive. `--new-only` excludes unchanged
artifacts admitted by the prospective baseline; it does not weaken the checks
applied to selected new publications.

### Media replacement history

An approved `visual replace` operation never rewrites the canonical text. Core
retains the superseded visual bytes, archives the previous canonical receipt as
an immutable revision, increments `revision`, and records
`supersedes_receipt_hash` on the new receipt. Verification follows the current
canonical package while the archived receipt preserves the audit chain.

## Baseline legacy publications

Review existing content, then record only the current unreceipted artifact
paths and hashes:

```bash
content-creator verify-publications --write-baseline
```

Commit `publication-receipts/baseline.json`, switch the policy to
`required-for-new-publications`, and run verification again. Changing a
baselined artifact invalidates its legacy exemption and requires a receipt.
Use `--replace-baseline` only after a deliberate review of the complete legacy
set.

## GitHub Actions

A downstream workspace can use an offline job such as:

```yaml
name: Publication provenance
on:
  pull_request:
    paths:
      - "content/**/published/**"
      - "profiles/**/versions/**"
      - "profiles/**/perspectives/**"
      - "publication-receipts/**"

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --frozen
      - run: uv run content-creator verify-publications
```

The receipt provides repository integrity evidence under the repository's
review and branch-protection trust boundary. It is not a cryptographic author
signature. Workspaces that require protection from an authorized committer
forging a receipt need a separate signing or CI-attestation policy.

## Semantic review and author decisions

When a run selects reusable perspective entries, Core asks the bounded
Perspective Evaluator to compare those entries with the exact publication
draft. The evaluator cannot produce deterministic failures and cannot approve
or reject publication. It may return:

- `review_required` for a possible omitted material qualification, possible
  counterposition, or ambiguous author/research/model attribution;
- `informational` for a possible new author position that may warrant a later
  perspective proposal.

Informational findings are recorded without blocking. Review-required findings
leave the run in `needs_author`, preserve
`publication-semantic-review.json` under the ignored run directory, and leave
the publication destination untouched.

The author may revise the draft and run publication again. If the author has
reviewed the unchanged draft and findings and decides they are acceptable,
record that decision explicitly:

```bash
content-creator publish <run-id> \
  --perspective-review-approved-by "Author" \
  --perspective-review-notes "Qualification is established in the preceding paragraph."
```

Core verifies that the approval refers to the exact reviewed draft and does not
invoke the evaluator again. Reviewer identity and notes remain in ignored run
evidence; the tracked receipt contains only the decision artifact hash and
finding codes. Set `semantic_review: off` only when the workspace deliberately
chooses deterministic provenance without model-assisted review.
