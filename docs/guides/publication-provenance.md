# Publication provenance and CI verification

Core writes a compact, repository-tracked receipt beside its ignored run
evidence whenever repository publication succeeds. The receipt binds the
published bytes to the originating run, pinned voice, direct author input,
selected perspective versions and entries, and the exact deterministic
perspective evaluation used at the publication boundary.

Receipts live under `publication-receipts/` by default. They contain hashes and
minimal provenance classifications, not prompts, drafts, feedback, research
notes, or author-contribution text.

## Verify publications offline

Run the verifier in a workspace or in CI:

```bash
content-creator verify-publications
```

The command makes no provider or network call. It checks publication hashes,
receipt schemas, originating status, pinned voice manifests, perspective
manifests, approved entry hashes, and the recorded deterministic evaluation.
An inactive context cannot authorize a new publication; historical receipts
continue to verify their immutable version after a later deactivation.

Configure enforcement in `content-creator.yaml`:

```yaml
publication_provenance:
  policy: required-for-new-publications
  receipts_directory: publication-receipts
```

Supported policies are:

- `off`: skip verification;
- `advisory`: report findings and exit successfully;
- `required-for-new-publications`: require receipts except for an unchanged
  legacy baseline;
- `required`: require valid receipts for every configured publication.

New generated workspaces use prospective enforcement with an empty baseline.
Existing workspaces remain advisory until deliberately migrated.

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
